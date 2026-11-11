"""Fill the README results section from reports/*.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def _p(x):
    return "—" if x is None else f"{x * 100:.1f}%"


NAMES = {"seasonal_naive": "Seasonal naive (baseline)", "moving_average": "Moving average",
         "holt_winters": "Holt-Winters", "gbm": "Gradient boosting", "selected_per_category": "Best per category"}


def build() -> str:
    bt = json.loads((ROOT / "reports" / "backtest.json").read_text())
    q = json.loads((ROOT / "reports" / "quality.json").read_text())
    sim = json.loads((ROOT / "reports" / "reorder_simulation.json").read_text())
    reg = json.loads((ROOT / "models" / "registry.json").read_text())
    mon = json.loads((ROOT / "reports" / "monitoring.json").read_text())

    ho = {r["model"]: r for r in bt["holdout_overall"]}
    base = ho["seasonal_naive"]["wape"]
    s = f"Updated automatically by the weekly retraining job. Data up to {bt['as_of']}.\n\n"

    s += ("### Forecast error on the last 28 days (held out)\n\n"
          "| Model | WAPE | vs baseline | MASE | 80% range coverage |\n|---|---|---|---|---|\n")
    for m in [k for k in NAMES if k != "selected_per_category"]:
        r = ho[m]
        delta = "—" if m == "seasonal_naive" else f"{(r['wape'] / base - 1) * 100:+.0f}%"
        s += f"| {NAMES[m]} | {_p(r['wape'])} | {delta} | {r['mase']:.2f} | {_p(r['coverage_80'])} |\n"
    sel = list(bt["selection_per_category"].values())
    picks = ", ".join(f"{NAMES[m].lower()} for {sel.count(m)}" for m in dict.fromkeys(sel))
    s += (f"\nThe live model uses the best model per category, chosen on the backtest ({picks} of {len(sel)} "
          f"categories): {_p(ho['selected_per_category']['wape'])} WAPE.\n")
    fh = {r["model"]: r for r in bt["festival_days_holdout"]}
    if "gbm" in fh and "seasonal_naive" in fh:
        s += (f"\nOn festival days, gradient boosting had {_p(fh['gbm']['wape'])} WAPE vs "
              f"{_p(fh['seasonal_naive']['wape'])} for the baseline. All models still under-forecast festivals.\n")

    s += (f"\n### Reorder simulation ({sim['days']} days, simulated)\n\n"
          "| Policy | Out-of-stock product-days | Lost sales (units) | Fill rate | Avg stock held (units) |\n"
          "|---|---|---|---|---|\n")
    label = {"fixed": "Current fixed rule", "forecast_sl90": "Forecast-based, 90% service",
             "forecast_sl95": "Forecast-based, 95% service", "forecast_sl98": "Forecast-based, 98% service"}
    for r in sim["results"]:
        s += (f"| {label.get(r['policy'], r['policy'])} | {r['stockout_product_days']} | {r['lost_units']:.0f} | "
              f"{_p(r['fill_rate'])} | {r['avg_units_on_hand']:.0f} |\n")

    s += "\n### Data checks (against problems planted in the synthetic data)\n\n"
    s += "| Check | Planted | Flagged | Precision | Recall |\n|---|---|---|---|---|\n"
    for r in q["scores"]:
        s += (f"| {r['check'].replace('_', ' ').capitalize()} | {r['planted']} | {r['flagged']} | {_p(r['precision'])} | "
              f"{_p(r['recall'])} |\n")

    s += "\n### Model history\n\n| Version | Holdout WAPE | Previous model, same days | Result |\n|---|---|---|---|\n"
    for v in reg["versions"][-6:]:
        ch = "—" if v["champion_wape_on_same_holdout"] is None else _p(v["champion_wape_on_same_holdout"])
        res = {"production": "live", "archived": "replaced later", "rejected": "rejected"}[v["status"]]
        s += f"| {v['version']} | {_p(v['holdout_wape_selected'])} | {ch} | {res} |\n"
    d = mon["latest_drift"]
    if mon["history"]:
        h = mon["history"][-1]
        s += (f"\nLast week's live forecast error was {_p(h['live_wape'])} (holdout at training: "
              f"{_p(h['holdout_wape_of_model'])}). ")
    s += f"Drift check: {'alert' if d['alert'] else 'no drift detected'}.\n"
    return s


def main():
    p = ROOT / "README.md"
    txt = p.read_text()
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), START + "\n" + build() + END, txt, flags=re.S)
    p.write_text(new)


if __name__ == "__main__":
    main()
