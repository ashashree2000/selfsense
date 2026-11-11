"""End-to-end retraining job (run weekly by GitHub Actions, or by hand).

  1. "New days arrive": export the synthetic world up to as_of (default: last as_of + 7 days)
  2. ETL + validation, data-quality checks (scored against planted labels)
  3. Rolling-origin backtest + holdout for all models; per-category selection
  4. Version the candidate (date + short hash), save model card / metrics / GBM binary
  5. Champion-challenger: promote only if candidate holdout WAPE is not worse than the
     current production config on the SAME holdout by more than PROMOTION_THRESHOLD
  6. Monitoring: score the previously published forecasts against the newly arrived
     actuals, and run a drift check
  7. Publish app/forecasts.json (read by the Insights tab and the API)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from forecasting import models as fmodels
from forecasting.backtest import conformal_intervals, run_backtest
from forecasting.metrics import wape
from inventory.reorder import forecast_selected, residual_sigma, simulate, suggestions, write_sim_report
from mlops.brief import build_brief
from pipeline import etl
from pipeline.generate_data import export, simulate_world
from quality.checks import evaluate, run_checks, write_report

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "models" / "registry.json"
PUBLISH = ROOT / "app" / "forecasts.json"
MONITOR = ROOT / "reports" / "monitoring.json"
PROMOTION_THRESHOLD = 0.02  # candidate may be at most 2% (relative) worse than champion
BOOTSTRAP_AS_OF = "2026-10-03"
H = 14


def _sha(path_or_bytes) -> str:
    b = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()
    return hashlib.sha256(b).hexdigest()


def code_hash() -> str:
    files = ["forecasting/models.py", "forecasting/backtest.py", "pipeline/etl.py", "pipeline/generate_data.py"]
    return _sha(b"".join((ROOT / f).read_bytes() for f in files))[:12]


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {"production": None, "current_as_of": None, "promotion_threshold": PROMOTION_THRESHOLD, "versions": []}


def selected_wape(ho_all: pd.DataFrame, selection: dict) -> float:
    parts = [ho_all[(ho_all["category"] == c) & (ho_all["model"] == m) & ho_all["valid"]] for c, m in selection.items()]
    g = pd.concat(parts)
    return wape(g["units"], g["yhat"])


def live_accuracy(prev: dict, pdaily: pd.DataFrame, as_of: str) -> dict | None:
    """Score previously published forecasts on days that have now arrived."""
    rows = []
    for p in prev.get("products", []):
        for d, yh in zip(p["forecast"]["dates"], p["forecast"]["yhat"]):
            if prev["meta"]["as_of"] < d <= as_of:
                rows.append((p["productId"], d, yh))
    if not rows:
        return None
    f = pd.DataFrame(rows, columns=["productId", "date", "yhat"]).merge(pdaily, on=["productId", "date"])
    v = f[(f["stockout"] == 0) & (f["is_dry_day"] == 0)]
    return {"forecast_made_at": prev["meta"]["as_of"], "model_version": prev["meta"]["model_version"],
            "scored_through": as_of, "days": int(f["date"].nunique()), "n": int(len(v)),
            "live_wape": round(wape(v["units"], v["yhat"]), 4),
            "backtest_wape_of_model": prev["model_info"]["backtest_wape_selected"],
            "holdout_wape_of_model": prev["model_info"]["holdout_wape_selected"]}


def drift_check(pdaily: pd.DataFrame, as_of: str, recent_days: int = 28, live: dict | None = None) -> dict:
    d = pdaily[(pdaily["is_dry_day"] == 0) & (pdaily["is_festival"] == 0)]
    tot = d.groupby("date")["units"].sum()
    cut = (pd.Timestamp(as_of) - pd.Timedelta(days=recent_days)).strftime("%Y-%m-%d")
    recent, train = tot[tot.index > cut], tot[tot.index <= cut]
    ks = ks_2samp(recent.values, train.values)
    shift = float(recent.mean() / train.mean() - 1)
    err_ratio = None
    if live:
        err_ratio = round(live["live_wape"] / live["holdout_wape_of_model"], 3)
    alert = bool((ks.pvalue < 0.01 and abs(shift) > 0.15) or (err_ratio is not None and err_ratio > 1.5))
    return {"recent_window_days": recent_days, "recent_mean_daily_units": round(float(recent.mean()), 1),
            "training_mean_daily_units": round(float(train.mean()), 1), "mean_shift": round(shift, 4),
            "ks_stat": round(float(ks.statistic), 4), "ks_pvalue": round(float(ks.pvalue), 5),
            "live_to_holdout_error_ratio": err_ratio, "alert": alert,
            "rule": "alert if (KS p<0.01 and |mean shift|>15%) or live WAPE > 1.5x holdout WAPE"}


def run(as_of: str | None = None, do_simulate: bool = True, verbose: bool = True) -> dict:
    reg = load_registry()
    if as_of is None:
        as_of = (BOOTSTRAP_AS_OF if not reg["current_as_of"]
                 else (pd.Timestamp(reg["current_as_of"]) + pd.Timedelta(days=7)).strftime("%Y-%m-%d"))
    if as_of > "2027-06-16":
        raise SystemExit(f"as_of {as_of} is past the end of the synthetic world (2027-06-30 minus horizon)")
    log = (lambda *a: print(f"[{as_of}]", *a)) if verbose else (lambda *a: None)  # noqa: E731

    # 1-2. data, ETL, quality
    world = simulate_world()
    export(world, as_of)
    raw = ROOT / "data" / "raw" / f"db_{as_of}.json"
    res = etl.run(raw, as_of)
    pdaily, cdaily, tables = res["product_daily"], res["category_daily"], res["tables"]
    labels = json.loads((ROOT / "data" / "truth" / "planted_anomalies.json").read_text())
    qres = run_checks(tables, cdaily)
    qscores = evaluate(qres, labels)
    qrep = write_report(qres, qscores, as_of)
    log("ETL ok:", res["report"]["row_counts"])

    # 3. backtest
    bt_rep, bt, ho_all = run_backtest(pdaily, as_of)
    selection = bt_rep["selection_per_category"]
    cand_wape = selected_wape(ho_all, selection)
    bt_sel = {r["model"]: r for r in bt_rep["backtest_overall"]}["selected_per_category"]["wape"]
    log("selection:", selection, "holdout WAPE:", round(cand_wape, 4))

    # 4. version + artifacts
    data_hash = _sha(raw)[:12]
    chash = code_hash()
    version = f"v{as_of.replace('-', '')}-{hashlib.sha256((chash + data_hash).encode()).hexdigest()[:7]}"
    art = ROOT / "models" / "artifacts" / version
    art.mkdir(parents=True, exist_ok=True)

    # 5. champion-challenger on the same holdout
    champ = next((v for v in reg["versions"] if v["version"] == reg["production"]), None)
    champ_wape = selected_wape(ho_all, champ["selection"]) if champ else None
    if champ is None:
        promote, reason = True, "bootstrap: no production model yet"
    elif cand_wape <= champ_wape * (1 + PROMOTION_THRESHOLD):
        promote, reason = True, f"candidate {cand_wape:.4f} <= champion {champ_wape:.4f} x (1+{PROMOTION_THRESHOLD})"
    else:
        promote, reason = False, f"candidate {cand_wape:.4f} worse than champion {champ_wape:.4f} beyond threshold"
    prod_selection = selection if promote else champ["selection"]
    prod_version = version if promote else champ["version"]
    log("promotion:", promote, reason)

    # 6. monitoring
    prev = json.loads(PUBLISH.read_text()) if PUBLISH.exists() else None
    live = live_accuracy(prev, pdaily, as_of) if prev and prev["meta"]["as_of"] < as_of else None
    drift = drift_check(pdaily, as_of, live=live)
    mon = json.loads(MONITOR.read_text()) if MONITOR.exists() else {"data": "SYNTHETIC", "history": []}
    if live:
        mon["history"] = [h for h in mon["history"] if h["scored_through"] != as_of] + [live]
    mon["latest_drift"] = dict(drift, as_of=as_of)
    MONITOR.write_text(json.dumps(mon, indent=1))

    # 7. production forecast for the next H days + intervals + reorder suggestions
    fc = forecast_selected(pdaily, as_of, prod_selection, horizon=H)
    if fmodels.LAST_GBM is not None and "gbm" in prod_selection.values():
        joblib.dump(fmodels.LAST_GBM, art / "gbm.joblib")
    fc = conformal_intervals(bt, fc.assign(is_dry_day=etl.calendar_features(fc["date"])["is_dry_day"].values))
    products = tables["products"]
    meta = json.loads((ROOT / "data" / "truth" / "product_meta.json").read_text())
    last = pdaily[pdaily["date"] == as_of].set_index("productId")["closing_stock"].to_dict()
    sigma = residual_sigma(bt, prod_selection)
    lead = {int(k): v["lead_time"] for k, v in meta.items()}
    sugg = suggestions(fc, products, last, sigma, lead)

    hist_start = (pd.Timestamp(as_of) - pd.Timedelta(days=41)).strftime("%Y-%m-%d")
    recent = pdaily[pdaily["date"] >= hist_start]
    prod_out = []
    for p in products.itertuples():
        f = fc[fc["productId"] == p.id].sort_values("h")
        h = recent[recent["productId"] == p.id].sort_values("date")
        prod_out.append({"productId": int(p.id), "name": p.name, "category": p.category,
                         "model": f["model"].iloc[0],
                         "history": {"dates": h["date"].tolist(), "units": h["units"].astype(int).tolist(),
                                     "stockout": h["stockout"].astype(int).tolist()},
                         "forecast": {"dates": f["date"].tolist(), "yhat": f["yhat"].round(2).tolist(),
                                      "lo": f["lo"].round(2).tolist(), "hi": f["hi"].round(2).tolist()}})
    cat_out = []
    fc["category"] = fc["productId"].map(products.set_index("id")["category"])
    for cat, g in fc.groupby("category"):
        s = g.groupby("date")[["yhat", "lo", "hi"]].sum().sort_index()
        hh = recent[recent["category"] == cat].groupby("date")["units"].sum().sort_index()
        cat_out.append({"category": cat, "model": prod_selection[cat], "dates": s.index.tolist(),
                        "yhat": s["yhat"].round(1).tolist(), "lo_sum": s["lo"].round(1).tolist(),
                        "hi_sum": s["hi"].round(1).tolist(),
                        "history": {"dates": hh.index.tolist(), "units": hh.astype(int).tolist()}})

    ho = {r["model"]: r for r in bt_rep["holdout_overall"]}
    entry = {"version": version, "as_of": as_of, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "code_hash": chash, "data_hash": data_hash, "selection": selection,
             "holdout_wape_selected": round(cand_wape, 4), "backtest_wape_selected": round(bt_sel, 4),
             "holdout_wape_seasonal_naive": ho["seasonal_naive"]["wape"],
             "holdout_coverage_80_selected": ho["selected_per_category"]["coverage_80"],
             "champion_wape_on_same_holdout": None if champ_wape is None else round(champ_wape, 4),
             "status": "production" if promote else "rejected", "decision": reason}
    for v in reg["versions"]:
        if promote and v["status"] == "production":
            v["status"] = "archived"
    reg["versions"] = [v for v in reg["versions"] if v["version"] != version] + [entry]
    reg["production"] = prod_version
    reg["current_as_of"] = as_of
    reg["promotion_threshold"] = PROMOTION_THRESHOLD
    REGISTRY.write_text(json.dumps(reg, indent=1))
    (art / "model_card.json").write_text(json.dumps({**entry, "horizon_days": H, "hgb_params": fmodels.HGB_PARAMS,
                                                     "features": fmodels.FEATURES, "data": "SYNTHETIC"}, indent=1))
    (art / "metrics.json").write_text(json.dumps({"holdout_overall": bt_rep["holdout_overall"],
                                                  "backtest_overall": bt_rep["backtest_overall"]}, indent=1))
    prod_entry = next(v for v in reg["versions"] if v["version"] == prod_version)

    payload = {
        "meta": {"app": "SelfSense", "data": "SYNTHETIC — generated demo data, not a real shop",
                 "as_of": as_of, "forecast_start": fc["date"].min(), "horizon_days": H,
                 "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "model_version": prod_version},
        "model_info": {"version": prod_version, "trained_through": as_of, "selection": prod_selection,
                       "holdout_wape_selected": prod_entry["holdout_wape_selected"],
                       "backtest_wape_selected": prod_entry["backtest_wape_selected"],
                       "holdout_wape_seasonal_naive": prod_entry["holdout_wape_seasonal_naive"],
                       "holdout_coverage_80": prod_entry["holdout_coverage_80_selected"],
                       "holdout_overall": bt_rep["holdout_overall"],
                       "last_decision": {"candidate": version, "promoted": promote, "reason": reason},
                       "promotion_rule": f"promote if candidate holdout WAPE <= champion WAPE x (1+{PROMOTION_THRESHOLD})",
                       "registry_versions": len(reg["versions"])},
        "products": prod_out,
        "category_forecast": cat_out,
        "reorder_suggestions": sugg,
        "quality": {"counts": qrep["counts"], "scores": qscores,
                    "alerts": {k: v[-8:] for k, v in qrep["alerts"].items()}},
        "monitoring": {"history": mon["history"], "drift": drift},
    }
    payload["brief"] = build_brief(payload)
    PUBLISH.write_text(json.dumps(payload, default=float))
    # the demo app loads the same synthetic snapshot the forecasts were built from
    demo = ROOT / "app" / "data"
    demo.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(raw, demo / "demo_db.json")
    shutil.copyfile(raw.with_suffix(".xlsx"), demo / "demo_db.xlsx")
    (ROOT / "reports" / "weekly_brief.json").write_text(json.dumps(payload["brief"], indent=1))
    log("published", PUBLISH.name, "production:", prod_version)

    if do_simulate:
        end = as_of
        start = (pd.Timestamp(as_of) - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
        sim = simulate(pdaily, world.latent, products, meta, prod_selection, sigma, start, end)
        write_sim_report(sim)
        log("simulation:", [(r["policy"], r["stockout_product_days"], r["avg_units_on_hand"]) for r in sim["results"]])
    return payload


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None, help="default: registry current_as_of + 7 days (bootstrap 2026-10-03)")
    ap.add_argument("--no-simulate", action="store_true")
    a = ap.parse_args(argv)
    run(a.as_of, do_simulate=not a.no_simulate)


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
