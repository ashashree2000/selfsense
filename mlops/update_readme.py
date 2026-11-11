"""Regenerate the README results section from reports/*.json (no hand-copied numbers)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def _p(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def build() -> str:
    bt = json.loads((ROOT / "reports" / "backtest.json").read_text())
    q = json.loads((ROOT / "reports" / "quality.json").read_text())
    sim = json.loads((ROOT / "reports" / "reorder_simulation.json").read_text())
    reg = json.loads((ROOT / "models" / "registry.json").read_text())
    mon = json.loads((ROOT / "reports" / "monitoring.json").read_text())

    ho = {r["model"]: r for r in bt["holdout_overall"]}
    base = ho["seasonal_naive"]["wape"]
    order = ["seasonal_naive", "moving_average", "holt_winters", "gbm", "selected_per_category"]
    s = (f"_Auto-generated from `reports/*.json` by `mlops/update_readme.py`. Data as of **{bt['as_of']}**. "
         "All data is SYNTHETIC._\n\n")
    s += ("### Forecast accuracy — holdout (last 28 days, never used for model selection)\n\n"
          "Product-level daily forecasts, 14-day horizon. Stock-out and dry days excluded from scoring.\n\n"
          "| Model | WAPE | vs seasonal naive | MASE | Bias | 80% interval coverage |\n|---|---|---|---|---|---|\n")
    for m in order:
        r = ho[m]
        s += (f"| {m} | {_p(r['wape'])} | {(r['wape'] / base - 1) * 100:+.1f}% | {r['mase']:.3f} | {_p(r['bias'])} | "
              f"{_p(r['coverage_80'])} |\n")
    bto = {r["model"]: r for r in bt["backtest_overall"]}
    s += (f"\nRolling-origin backtest ({len(bt['backtest_origins'])} origins, {bt['backtest_origins'][0]} → "
          f"{bt['backtest_origins'][-1]}): " + ", ".join(f"{m} WAPE {_p(bto[m]['wape'])}" for m in order) + ".\n")
    s += "\nModel selected per category (by backtest WAPE): " + ", ".join(
        f"{c} → {m}" for c, m in sorted(bt["selection_per_category"].items())) + ".\n"
    fb = {r["model"]: r for r in bt["festival_days_backtest"]}
    fh = {r["model"]: r for r in bt["festival_days_holdout"]}
    s += "\n**Festival days** (WAPE / bias):\n\n| Model | Backtest windows | Holdout |\n|---|---|---|\n"
    for m in order:
        a = fb.get(m)
        b = fh.get(m)
        s += (f"| {m} | {(_p(a['wape']) + ' / ' + _p(a['bias'])) if a else '—'} (n={a['n'] if a else 0}) | "
              f"{(_p(b['wape']) + ' / ' + _p(b['bias'])) if b else '—'} (n={b['n'] if b else 0}) |\n")

    s += ("\n### Data-quality checks vs planted anomalies\n\n| Check | Planted | Flagged | Precision | Recall |\n"
          "|---|---|---|---|---|\n")
    for r in q["scores"]:
        s += f"| {r['check']} | {r['planted']} | {r['flagged']} | {_p(r['precision'])} | {_p(r['recall'])} |\n"
    s += ("\nThe five rule-based checks are exact by construction on this synthetic data (each rule mirrors how the "
          "anomaly was planted). The statistical spike/drop detector is the honest test, and it is weak on "
          "low-count series.\n")

    s += (f"\n### Reorder policy — SIMULATED ({sim['window'][0]} → {sim['window'][1]}, {sim['days']} days, "
          f"{sim['products']} products, true latent demand replayed)\n\n"
          "| Policy | Stock-out product-days | Lost units | Fill rate | Avg units on hand | Avg stock value (₹) | Orders |\n"
          "|---|---|---|---|---|---|---|\n")
    for r in sim["results"]:
        s += (f"| {r['policy']} | {r['stockout_product_days']} | {r['lost_units']:.0f} | {_p(r['fill_rate'])} | "
              f"{r['avg_units_on_hand']} | {r['avg_stock_value']:,.0f} | {r['orders_placed']} |\n")

    s += ("\n### Model registry & monitoring\n\n"
          "| Version | Data as of | Holdout WAPE | Champion on same holdout | Status | Decision |\n")
    s += "|---|---|---|---|---|---|\n"
    for v in reg["versions"]:
        ch = "—" if v["champion_wape_on_same_holdout"] is None else _p(v["champion_wape_on_same_holdout"])
        s += (f"| {v['version']} | {v['as_of']} | {_p(v['holdout_wape_selected'])} | {ch} | {v['status']} | "
              f"{v['decision']} |\n")
    if mon["history"]:
        s += "\nLive accuracy of published forecasts (scored when the next week's data arrived):\n\n"
        s += "| Forecast made | Scored through | Model | Live WAPE | Holdout WAPE at training |\n|---|---|---|---|---|\n"
        for h in mon["history"]:
            s += (f"| {h['forecast_made_at']} | {h['scored_through']} | {h['model_version']} | {_p(h['live_wape'])} | "
                  f"{_p(h['holdout_wape_of_model'])} |\n")
    d = mon["latest_drift"]
    s += (f"\nLatest drift check ({d['as_of']}): recent {d['recent_window_days']}-day mean {d['recent_mean_daily_units']} "
          f"units/day vs {d['training_mean_daily_units']} before (shift {_p(d['mean_shift'])}), KS p = {d['ks_pvalue']}, "
          f"live/holdout error ratio = {d['live_to_holdout_error_ratio']} → **{'ALERT' if d['alert'] else 'no alert'}**.\n")
    return s


def main():
    p = ROOT / "README.md"
    txt = p.read_text()
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), START + "\n" + build() + END, txt, flags=re.S)
    p.write_text(new)


if __name__ == "__main__":
    main()
