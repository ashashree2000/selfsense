"""Rolling-origin backtest + untouched holdout.

Timeline for a given as_of (default settings):
  ... | backtest origins every 14 days (n_folds of them) | holdout: last 28 days (2 origins) |
- Each fold re-fits every model on data <= its origin and forecasts 14 days.
- Model SELECTION per category uses only the backtest folds.
- The HOLDOUT is scored once, after selection, and is never used to choose.
- 80% prediction intervals are split-conformal: per model x product x horizon
  bucket, the 10th/90th percentiles of backtest residuals are added to the
  point forecast. Coverage is then measured on the holdout.
- Days that are stock-outs (censored demand) or dry days are excluded from scoring.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from forecasting.metrics import bias, coverage, seasonal_scale, wape
from forecasting.models import MODEL_NAMES, forecast

ROOT = Path(__file__).resolve().parents[1]
H = 14
STEP = 14
N_FOLDS = 20
HOLDOUT_DAYS = 28
LOWER_Q, UPPER_Q = 0.10, 0.90


def origins_for(as_of: str, n_folds: int = N_FOLDS):
    a = pd.Timestamp(as_of)
    hold_start = a - pd.Timedelta(days=HOLDOUT_DAYS - 1)
    hold = [hold_start - pd.Timedelta(days=1) + pd.Timedelta(days=STEP * k) for k in range(HOLDOUT_DAYS // STEP)]
    bt = [hold_start - pd.Timedelta(days=1) - pd.Timedelta(days=STEP * k) for k in range(n_folds, 0, -1)]
    f = lambda xs: [x.strftime("%Y-%m-%d") for x in xs]  # noqa: E731
    return f(bt), f(hold)


def _scales(pdaily: pd.DataFrame, origin: str) -> dict:
    """Per-product MASE scale from training data up to the origin."""
    out = {}
    tr = pdaily[pdaily["date"] <= origin].sort_values("date")
    for pid, g in tr.groupby("productId"):
        valid = (g["stockout"] == 0) & (g["is_dry_day"] == 0)
        out[pid] = seasonal_scale(g["units"].to_numpy(), valid.to_numpy())
    return out


def run_origins(pdaily: pd.DataFrame, origins: list[str], phase: str, as_of: str, models=MODEL_NAMES) -> pd.DataFrame:
    act = pdaily[["productId", "date", "units", "stockout", "is_dry_day", "is_festival", "category"]]
    recs = []
    for o in origins:
        scales = _scales(pdaily, o)
        for m in models:
            fc = forecast(m, pdaily, o, H)
            fc = fc[fc["date"] <= as_of].merge(act, on=["productId", "date"], how="left")
            fc["model"], fc["origin"], fc["phase"] = m, o, phase
            fc["scale"] = fc["productId"].map(scales)
            recs.append(fc)
    df = pd.concat(recs, ignore_index=True)
    df["valid"] = (df["stockout"] == 0) & (df["is_dry_day"] == 0)
    df["err"] = df["yhat"] - df["units"]
    return df


def summarize(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    v = df[df["valid"]]
    rows = []
    for key, g in v.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        r = dict(zip(by, key))
        r.update(wape=wape(g["units"], g["yhat"]), bias=bias(g["units"], g["yhat"]),
                 mase=float((g["err"].abs() / g["scale"]).replace(np.inf, np.nan).mean()),
                 n=int(len(g)), actual_units=float(g["units"].sum()))
        rows.append(r)
    return pd.DataFrame(rows)


def conformal_intervals(bt: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:
    """Attach lo/hi to `target` using backtest residual quantiles per model x product x horizon bucket."""
    b = bt[bt["valid"]].copy()
    b["hb"] = np.where(b["h"] <= 7, 1, 2)
    b["res"] = b["units"] - b["yhat"]
    q = b.groupby(["model", "productId", "hb"])["res"].quantile([LOWER_Q, UPPER_Q]).unstack()
    q.columns = ["qlo", "qhi"]
    t = target.copy()
    t["hb"] = np.where(t["h"] <= 7, 1, 2)
    t = t.merge(q.reset_index(), on=["model", "productId", "hb"], how="left")
    t["lo"] = (t["yhat"] + t["qlo"].fillna(0)).clip(lower=0)
    t["hi"] = (t["yhat"] + t["qhi"].fillna(0)).clip(lower=0)
    dry = t.get("is_dry_day")
    if dry is not None:
        t.loc[dry == 1, ["lo", "hi"]] = 0.0
    return t.drop(columns=["hb", "qlo", "qhi"])


def run_backtest(pdaily: pd.DataFrame, as_of: str, n_folds: int = N_FOLDS, out_dir: Path | None = ROOT / "reports"):
    bt_origins, hold_origins = origins_for(as_of, n_folds)
    bt = run_origins(pdaily, bt_origins, "backtest", as_of)
    ho = run_origins(pdaily, hold_origins, "holdout", as_of)
    ho = conformal_intervals(bt, ho)

    bt_cat = summarize(bt, ["model", "category"])
    selection = (bt_cat.loc[bt_cat.groupby("category")["wape"].idxmin()]
                 .set_index("category")["model"].to_dict())

    def overall(df):
        return summarize(df.assign(_all="all"), ["model", "_all"]).drop(columns="_all")

    sel_ho = pd.concat([ho[(ho["category"] == c) & (ho["model"] == m)] for c, m in selection.items()])
    sel_bt = pd.concat([bt[(bt["category"] == c) & (bt["model"] == m)] for c, m in selection.items()])
    sel_ho = sel_ho.assign(model="selected_per_category")
    sel_bt = sel_bt.assign(model="selected_per_category")

    ho_all = pd.concat([ho, sel_ho])
    hv = ho_all[ho_all["valid"]]
    cov = (hv.groupby("model").apply(lambda g: coverage(g["units"], g["lo"], g["hi"]), include_groups=False)
           .rename("coverage_80").reset_index())
    fest_bt = summarize(pd.concat([bt, sel_bt])[lambda d: d["is_festival"] == 1].assign(_f=1), ["model", "_f"])
    fest_ho = summarize(ho_all[ho_all["is_festival"] == 1].assign(_f=1), ["model", "_f"])

    report = {
        "as_of": as_of,
        "data": "SYNTHETIC",
        "horizon_days": H,
        "backtest_origins": bt_origins,
        "holdout_origins": hold_origins,
        "scoring_excludes": "stock-out days (censored demand) and dry days",
        "interval": "80% split-conformal (backtest residual quantiles 10%/90% per model x product x horizon bucket)",
        "selection_per_category": selection,
        "backtest_overall": overall(pd.concat([bt, sel_bt])).round(4).to_dict("records"),
        "backtest_by_category": bt_cat.round(4).to_dict("records"),
        "holdout_overall": overall(ho_all).merge(cov, on="model").round(4).to_dict("records"),
        "holdout_by_category": summarize(ho_all, ["model", "category"]).round(4).to_dict("records"),
        "festival_days_backtest": fest_bt.drop(columns="_f", errors="ignore").round(4).to_dict("records"),
        "festival_days_holdout": fest_ho.drop(columns="_f", errors="ignore").round(4).to_dict("records"),
    }
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "backtest.json").write_text(json.dumps(report, indent=1))
        (out_dir / "backtest.md").write_text(to_markdown(report))
    return report, bt, ho_all


def _tbl(records, cols):
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = ""
    for r in records:
        body += "| " + " | ".join(
            (f"{r[c]:.3f}" if isinstance(r[c], float) else str(r[c])) for c in cols) + " |\n"
    return head + body


def to_markdown(r: dict) -> str:
    base = {x["model"]: x for x in r["holdout_overall"]}["seasonal_naive"]["wape"]
    ho = [dict(x, wape_vs_naive=(x["wape"] / base - 1)) for x in r["holdout_overall"]]
    md = f"# Forecast backtest (SYNTHETIC data, as of {r['as_of']})\n\n"
    md += (f"Horizon {r['horizon_days']} days. {len(r['backtest_origins'])} rolling backtest origins "
           f"({r['backtest_origins'][0]} .. {r['backtest_origins'][-1]}), holdout origins {r['holdout_origins']}.\n"
           f"Scoring excludes {r['scoring_excludes']}. Intervals: {r['interval']}.\n\n")
    md += "## Holdout (never used for selection)\n\n"
    md += _tbl(ho, ["model", "wape", "wape_vs_naive", "mase", "bias", "coverage_80", "n"])
    md += "\n## Backtest (used for selection)\n\n" + _tbl(r["backtest_overall"], ["model", "wape", "mase", "bias", "n"])
    md += "\n## Model selected per category (lowest backtest WAPE)\n\n"
    md += "\n".join(f"- {c}: {m}" for c, m in r["selection_per_category"].items()) + "\n"
    md += "\n## Festival days\n\nBacktest windows:\n\n" + _tbl(r["festival_days_backtest"], ["model", "wape", "bias", "n"])
    if r["festival_days_holdout"]:
        md += "\nHoldout:\n\n" + _tbl(r["festival_days_holdout"], ["model", "wape", "bias", "n"])
    md += "\n## Holdout by category\n\n" + _tbl(r["holdout_by_category"], ["model", "category", "wape", "mase", "bias", "n"])
    return md


if __name__ == "__main__":
    import sys
    as_of = sys.argv[1] if len(sys.argv) > 1 else "2026-09-30"
    pdaily = pd.read_parquet(ROOT / "data" / "processed" / "product_daily.parquet")
    rep, _, _ = run_backtest(pdaily, as_of)
    print(to_markdown(rep))
