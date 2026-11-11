"""Data-quality and anomaly checks on the raw DB tables + the daily table.

Each check returns a list of flagged keys (row ids, product ids, or
(date, category) pairs) plus human-readable alerts. `evaluate()` scores them
against the generator's planted labels (precision / recall).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPIKE_Z = 3.5


def _ledger_sorted(led: pd.DataFrame) -> pd.DataFrame:
    led = led.sort_values(["productId", "date", "id"]).copy()
    led["recon_balance"] = led.groupby("productId")["qtyChange"].cumsum()
    return led


def ledger_balance_mismatch(led):
    """balanceAfter recorded on the row disagrees with the balance rebuilt from qtyChange events."""
    led = _ledger_sorted(led)
    bad = led[led["balanceAfter"] != led["recon_balance"]]
    return bad["id"].astype(int).tolist(), [
        f"Ledger row {r.id} ({r.productName}, {r.date[:10]}): recorded balance {r.balanceAfter}, "
        f"rebuilt balance {r.recon_balance}" for r in bad.itertuples()]


def sale_at_zero_stock(led, sales):
    """A sale was recorded while the rebuilt ledger stock before it was already <= 0."""
    led = _ledger_sorted(led)
    led["before"] = led["recon_balance"] - led["qtyChange"]
    hits = led[(led["type"] == "Sale") & (led["before"] <= 0)]
    inv = set(hits["reference"])
    s = sales[sales["invoiceNo"].isin(inv)]
    return s["id"].astype(int).tolist(), [
        f"Sale {r.invoiceNo} ({r.productName}, {r.date[:10]}) recorded with zero stock in the ledger" for r in s.itertuples()]


def duplicate_sales(sales):
    """Same invoice, product, qty and timestamp recorded more than once (double submit)."""
    d = sales[sales.duplicated(subset=["invoiceNo", "productId", "qty", "date"], keep="first")]
    return d["id"].astype(int).tolist(), [f"Duplicate of sale {r.invoiceNo} ({r.productName}, {r.date[:10]})"
                                          for r in d.itertuples()]


def credit_sale_no_name(sales):
    """Credit sale without a customer name: the debt can't be attributed to anyone."""
    c = sales[(sales["paymentMode"] == "Credit") & (sales["customerName"].fillna("").astype(str).str.strip() == "")]
    return c["id"].astype(int).tolist(), [f"Credit sale {r.invoiceNo} ({r.date[:10]}, {r.total:.0f}) has no customer name"
                                          for r in c.itertuples()]


def shrinkage(products, led):
    """Recorded stockQty differs from the ledger-rebuilt stock -> unrecorded loss/breakage (or extra stock)."""
    bal = led.groupby("productId")["qtyChange"].sum()
    p = products.set_index("id")
    diff = (p["stockQty"] - bal.reindex(p.index).fillna(0)).astype(int)
    bad = diff[diff != 0]
    return bad.index.astype(int).tolist(), [
        f"{p.loc[i, 'name']}: shelf count {int(p.loc[i, 'stockQty'])} vs ledger {int(bal.get(i, 0))} "
        f"({'missing' if d < 0 else 'extra'} {abs(d)} units)" for i, d in bad.items()]


def demand_anomalies(cdaily: pd.DataFrame, z: float = SPIKE_Z):
    """Category-day sales far from a robust same-weekday baseline forecast.

    expected = median of the same weekday over the previous 4 weeks (valid days only);
    robust z-score uses the MAD of residuals within each category. Festival, dry,
    holiday and stock-out days are not scored (known causes).
    """
    spikes, drops, alerts = [], [], []
    for cat, g in cdaily.sort_values("date").groupby("category"):
        g = g.reset_index(drop=True)
        valid = (g["stockout"] == 0) & (g["is_dry_day"] == 0) & (g["is_festival"] == 0) & (g["is_holiday"] == 0)
        y = g["units"].where(valid)
        exp = pd.concat([y.shift(7 * k) for k in range(1, 5)], axis=1).median(axis=1, skipna=True)
        res = g["units"] - exp
        scored = valid & exp.notna() & (g.index >= 28)
        mad = np.nanmedian(np.abs(res[scored] - np.nanmedian(res[scored])))
        scale = 1.4826 * mad if mad > 0 else 1.0
        zs = res / scale
        for i in g.index[scored]:
            if zs[i] >= z:
                spikes.append((g.at[i, "date"], cat))
                alerts.append(f"Spike: {cat} on {g.at[i, 'date']} sold {int(g.at[i, 'units'])} vs ~{exp[i]:.0f} expected")
            elif zs[i] <= -z:
                drops.append((g.at[i, "date"], cat))
                alerts.append(f"Drop: {cat} on {g.at[i, 'date']} sold {int(g.at[i, 'units'])} vs ~{exp[i]:.0f} expected")
    return spikes, drops, alerts


def run_checks(tables: dict, cdaily: pd.DataFrame) -> dict:
    sales, led, products = tables["sales"], tables["stockLedger"], tables["products"]
    out = {}
    for name, (keys, alerts) in {
        "duplicate_sale": duplicate_sales(sales),
        "credit_sale_no_name": credit_sale_no_name(sales),
        "sale_at_zero_stock": sale_at_zero_stock(led, sales),
        "ledger_balance_mismatch": ledger_balance_mismatch(led),
        "shrinkage": shrinkage(products, led),
    }.items():
        out[name] = {"flagged": keys, "alerts": alerts}
    sp, dr, al = demand_anomalies(cdaily)
    out["demand_spike"] = {"flagged": sp, "alerts": [a for a in al if a.startswith("Spike")]}
    out["demand_drop"] = {"flagged": dr, "alerts": [a for a in al if a.startswith("Drop")]}
    return out


def evaluate(results: dict, labels: dict) -> list[dict]:
    rows = []
    for check, res in results.items():
        truth = labels.get(check, [])
        if check in ("demand_spike", "demand_drop"):
            truth = {(x["date"], x["category"]) for x in truth}
            pred = {tuple(x) for x in res["flagged"]}
        else:
            truth, pred = set(truth), set(res["flagged"])
        tp = len(truth & pred)
        rows.append({"check": check, "planted": len(truth), "flagged": len(pred), "true_positives": tp,
                     "precision": tp / len(pred) if pred else float("nan"),
                     "recall": tp / len(truth) if truth else float("nan")})
    return rows


def write_report(results: dict, scores: list[dict], as_of: str, out_dir: Path = ROOT / "reports") -> dict:
    rep = {"as_of": as_of, "data": "SYNTHETIC", "scores": scores,
           "alerts": {k: v["alerts"][-50:] for k, v in results.items()},
           "counts": {k: len(v["flagged"]) for k, v in results.items()}}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "quality.json").write_text(json.dumps(rep, indent=1, default=str))
    md = f"# Data-quality checks (SYNTHETIC data, as of {as_of})\n\nScored against the anomalies planted by the generator.\n\n"
    md += "| check | planted | flagged | TP | precision | recall |\n|---|---|---|---|---|---|\n"
    for s in scores:
        md += (f"| {s['check']} | {s['planted']} | {s['flagged']} | {s['true_positives']} | "
               f"{s['precision']:.2f} | {s['recall']:.2f} |\n")
    (out_dir / "quality.md").write_text(md)
    return rep
