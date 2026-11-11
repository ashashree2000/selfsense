"""Forecast-based reorder policy and a SIMULATED comparison with the fixed rule.

Forecast policy (per product, reviewed daily):
    protection  = lead_time + 1 day (lead time can slip by one day)
    ROP         = sum(forecast over protection days) + z * sigma_daily * sqrt(protection)
    order-up-to = ROP + sum(forecast over `cover_days` after that)
    if stock + on_order <= ROP: order (order-up-to - stock - on_order)
sigma_daily is the std of the production model's backtest residuals for that product.

Fixed rule (what the app's `reorderLevel` field implies, and what generated the
synthetic history): if stock + on_order <= reorderLevel, order a fixed quantity.

The simulation replays TRUE latent demand from the generator (data/truth), so
lost sales during stock-outs are counted, which real sales data can't show.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from forecasting.models import forecast

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {"service_level": 0.95, "cover_days": 7, "default_lead_time": 3}


def residual_sigma(bt: pd.DataFrame, selection: dict) -> dict:
    """Std of daily backtest residuals per product for its category's selected model."""
    b = bt[bt["valid"]]
    out = {}
    for cat, m in selection.items():
        g = b[(b["category"] == cat) & (b["model"] == m)]
        for pid, gg in g.groupby("productId"):
            out[int(pid)] = float((gg["units"] - gg["yhat"]).std())
    return out


def forecast_selected(pdaily: pd.DataFrame, origin: str, selection: dict, horizon: int = 14) -> pd.DataFrame:
    cats = pdaily.drop_duplicates("productId").set_index("productId")["category"]
    parts = []
    for m in set(selection.values()):
        f = forecast(m, pdaily, origin, horizon)
        keep = [pid for pid in f["productId"].unique() if selection.get(cats[pid]) == m]
        parts.append(f[f["productId"].isin(keep)].assign(model=m))
    return pd.concat(parts, ignore_index=True)


def policy_levels(fc_p: np.ndarray, sigma: float, lead: int, service_level: float, cover_days: int):
    prot = lead + 1
    z = norm.ppf(service_level)
    rop = fc_p[:prot].sum() + z * sigma * np.sqrt(prot)
    up_to = rop + fc_p[prot:prot + cover_days].sum()
    return float(rop), float(up_to)


def suggestions(fc: pd.DataFrame, products: pd.DataFrame, stock: dict, sigma: dict, lead: dict,
                service_level=DEFAULTS["service_level"], cover_days=DEFAULTS["cover_days"]) -> list[dict]:
    out = []
    for p in products.itertuples():
        f = fc[fc["productId"] == p.id].sort_values("h")["yhat"].to_numpy()
        L = int(lead.get(p.id, DEFAULTS["default_lead_time"]))
        rop, up_to = policy_levels(f, sigma.get(p.id, 0.0), L, service_level, cover_days)
        s = int(stock.get(p.id, 0))
        qty = int(np.ceil(up_to - s)) if s <= rop else 0
        daily = f[:7].mean() if len(f) else 0
        out.append({"productId": int(p.id), "productName": p.name, "category": p.category,
                    "supplierId": int(p.supplierId), "current_stock": s, "lead_time_days": L,
                    "reorder_point": round(rop, 1), "order_up_to": round(up_to, 1), "suggested_qty": max(qty, 0),
                    "days_of_cover": round(s / daily, 1) if daily > 0 else None,
                    "fixed_rule_reorder_level": int(p.reorderLevel),
                    "fixed_rule_would_order": bool(s <= p.reorderLevel)})
    return sorted(out, key=lambda r: (-r["suggested_qty"], r["days_of_cover"] or 999))


def simulate(pdaily: pd.DataFrame, latent: pd.DataFrame, products: pd.DataFrame, meta: dict, selection: dict,
             sigma: dict, start: str, end: str, service_levels=(0.90, 0.95, 0.98), cover_days=7, seed=7) -> dict:
    days = pd.date_range(start, end).strftime("%Y-%m-%d").tolist()
    dem = latent[(latent["date"] >= start) & (latent["date"] <= end)].pivot(index="date", columns="productId",
                                                                          values="latent_demand").reindex(days)
    first = pdaily[pdaily["date"] == days[0]].set_index("productId")["opening_stock"].clip(lower=0)
    # weekly re-forecast with the selected models, using only observed history up to each origin
    origins = days[::7]
    fcs = {}
    for o in origins:
        prev = (pd.Timestamp(o) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        fcs[o] = forecast_selected(pdaily, prev, selection, horizon=21)

    def run(policy: str, sl: float | None):
        rng = np.random.default_rng(seed)
        stock = {int(p): float(first.get(p, 0)) for p in products["id"]}
        pipeline = []  # (arrival_idx, pid, qty)
        tot = dict(demand=0.0, sold=0.0, lost=0.0, stockout_days=0, stock_units=0.0, stock_value=0.0, orders=0)
        cost = products.set_index("id")["costPrice"].to_dict()
        rl = products.set_index("id")["reorderLevel"].to_dict()
        for i, d in enumerate(days):
            for a in [x for x in pipeline if x[0] == i]:
                stock[a[1]] += a[2]
            pipeline = [x for x in pipeline if x[0] != i]
            o = origins[i // 7]
            off = i - origins.index(o) * 7  # days since forecast origin
            for pid in stock:
                dmd = float(dem.at[d, pid]) if pd.notna(dem.at[d, pid]) else 0.0
                sold = min(dmd, stock[pid])
                stock[pid] -= sold
                tot["demand"] += dmd
                tot["sold"] += sold
                tot["lost"] += dmd - sold
                tot["stockout_days"] += int(dmd > sold)
                tot["stock_units"] += stock[pid]
                tot["stock_value"] += stock[pid] * cost[pid]
                on_order = sum(x[2] for x in pipeline if x[1] == pid)
                pos = stock[pid] + on_order
                L = int(meta[str(pid)]["lead_time"])
                if policy == "fixed":
                    q = meta[str(pid)]["order_qty"] if pos <= rl[pid] else 0
                else:
                    f = fcs[o]
                    fp = f[f["productId"] == pid].sort_values("h")["yhat"].to_numpy()[off + 1:]
                    rop, up_to = policy_levels(fp, sigma.get(pid, 0.0), L, sl, cover_days)
                    q = int(np.ceil(up_to - pos)) if pos <= rop else 0
                if q > 0:
                    lt = L + int(rng.integers(0, 2))
                    pipeline.append((i + lt, pid, q))
                    tot["orders"] += 1
        n = len(days) * len(stock)
        return {"policy": policy if policy == "fixed" else f"forecast_sl{int(sl * 100)}",
                "stockout_product_days": tot["stockout_days"],
                "stockout_rate": round(tot["stockout_days"] / n, 4),
                "lost_units": round(tot["lost"], 1), "fill_rate": round(tot["sold"] / tot["demand"], 4),
                "avg_units_on_hand": round(tot["stock_units"] / len(days), 1),
                "avg_stock_value": round(tot["stock_value"] / len(days), 0),
                "orders_placed": tot["orders"]}

    rows = [run("fixed", None)] + [run("forecast", sl) for sl in service_levels]
    return {"data": "SYNTHETIC (simulated on true latent demand)", "window": [start, end], "days": len(days),
            "products": int(len(products)), "cover_days": cover_days, "reforecast_every_days": 7, "results": rows}


def write_sim_report(sim: dict, out_dir: Path = ROOT / "reports"):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reorder_simulation.json").write_text(json.dumps(sim, indent=1))
    md = (f"# Reorder policy simulation (SIMULATED on SYNTHETIC data)\n\nWindow {sim['window'][0]} .. "
          f"{sim['window'][1]} ({sim['days']} days, {sim['products']} products). True latent demand replayed; "
          f"forecasts refreshed every {sim['reforecast_every_days']} days using only past data.\n\n")
    cols = ["policy", "stockout_product_days", "stockout_rate", "lost_units", "fill_rate", "avg_units_on_hand",
            "avg_stock_value", "orders_placed"]
    md += "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for r in sim["results"]:
        md += "| " + " | ".join(str(r[c]) for c in cols) + " |\n"
    (out_dir / "reorder_simulation.md").write_text(md)
