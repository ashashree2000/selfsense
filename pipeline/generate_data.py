"""Seeded SYNTHETIC data generator in the app's exact `DB` schema.

Simulates a single liquor shop day by day over a long "world" period
(2025-07-01 .. 2027-06-30). `export(as_of)` slices the world up to a given
date, which is how the scheduled retraining job simulates "new days arriving".

Everything produced here is synthetic. Brand names are fictional.

Outputs (for a given as_of):
  data/raw/db_<as_of>.json         -> DB object (same shape as the app's localStorage)
  data/raw/db_<as_of>.xlsx         -> workbook the app's existing "Load a Backup Excel File" import reads
  data/truth/latent_demand.parquet -> true (uncensored) demand per product-day, for simulation only
  data/truth/planted_anomalies.json-> ground-truth labels for the data-quality checks
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.calendar_config import DRY_DAYS, FESTIVALS, is_payday

SEED = 42
WORLD_START = date(2025, 7, 1)
WORLD_END = date(2027, 6, 30)
DEFAULT_AS_OF = "2026-09-30"
ROOT = Path(__file__).resolve().parents[1]

CATEGORIES = ["90ml", "150ml", "180ml", "375ml", "750ml", "Wine", "Beer"]
EXPENSE_CATEGORIES = ["Rent", "Electricity", "Salary", "Transport", "Maintenance", "Licence/Excise Fee", "Other"]

SUPPLIERS = [
    {"id": 1, "name": "Eastern Spirits Distributors", "phone": "", "address": "Guwahati", "gst": ""},
    {"id": 2, "name": "Kamrup Beverages", "phone": "", "address": "Guwahati", "gst": ""},
    {"id": 3, "name": "Valley Wine & Beer Traders", "phone": "", "address": "Guwahati", "gst": ""},
]

# (base name, category, cost, sell, base daily demand, supplier, lead_time_days, seasonal profile)
PRODUCT_SPECS = [
    ("Silver Crest Whisky", "90ml", 62, 80, 9.0, 1, 2, "spirit"),
    ("Silver Crest Whisky", "180ml", 120, 155, 6.0, 1, 2, "spirit"),
    ("Silver Crest Whisky", "750ml", 470, 610, 1.6, 1, 2, "spirit"),
    ("Red Kite Rum", "90ml", 55, 72, 6.5, 1, 2, "spirit"),
    ("Red Kite Rum", "180ml", 105, 140, 4.0, 1, 2, "spirit"),
    ("Red Kite Rum", "375ml", 210, 275, 2.0, 1, 2, "spirit"),
    ("Blue Hill Vodka", "180ml", 130, 170, 3.0, 2, 3, "spirit"),
    ("Blue Hill Vodka", "750ml", 520, 680, 1.1, 2, 3, "spirit"),
    ("Copper Leaf Brandy", "90ml", 58, 75, 4.5, 2, 3, "spirit"),
    ("Copper Leaf Brandy", "375ml", 220, 290, 1.5, 2, 3, "spirit"),
    ("Golden Field Whisky", "150ml", 95, 125, 3.5, 1, 2, "spirit"),
    ("Golden Field Whisky", "375ml", 235, 305, 1.8, 1, 2, "spirit"),
    ("Valley Red Wine", "Wine", 380, 520, 0.9, 3, 4, "wine"),
    ("Sunrise White Wine", "Wine", 360, 490, 0.6, 3, 4, "wine"),
    ("Northfield Lager", "Beer", 110, 150, 10.0, 3, 4, "beer"),
    ("Monsoon Strong Beer", "Beer", 120, 165, 8.0, 3, 4, "beer"),
]

LOSS_KINDS = [("Breakage - Loading/Unloading", "Bottle broken while unloading"),
              ("Breakage - In Transit", "Cracked in transit"),
              ("Leakage", "Seal leaking, removed from shelf")]

DOW = np.array([0.85, 0.80, 0.85, 0.95, 1.15, 1.40, 1.30])  # Mon..Sun


def month_factor(profile: str, m: int) -> float:
    if profile == "beer":   # hotter months up
        return {3: 1.1, 4: 1.25, 5: 1.35, 6: 1.3, 7: 1.15, 8: 1.1, 9: 1.05, 11: 0.85, 12: 0.8, 1: 0.75, 2: 0.85}.get(m, 1.0)
    if profile == "wine":
        return {12: 1.5, 1: 1.2, 2: 1.1}.get(m, 1.0)
    return {11: 1.1, 12: 1.2, 1: 1.2, 2: 1.05, 6: 0.92, 7: 0.9}.get(m, 1.0)  # spirits: winter up


@dataclass
class World:
    db: dict
    latent: pd.DataFrame
    anomalies: dict = field(default_factory=dict)


def _iso(d: date, hh: int, mm: int, ss: int = 0) -> str:
    """App stores new Date().toISOString() (UTC). hh:mm is UTC."""
    return datetime(d.year, d.month, d.day, hh, mm, ss).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def simulate_world(seed: int = SEED) -> World:
    rng = np.random.default_rng(seed)
    days = [WORLD_START + timedelta(days=i) for i in range((WORLD_END - WORLD_START).days + 1)]

    products = []
    for i, (name, cat, cost, sell, base, sup, lt, prof) in enumerate(PRODUCT_SPECS, start=1):
        products.append({
            "id": i, "name": f"{name} {cat}" if cat not in ("Wine", "Beer") else name,
            "brand": name, "category": cat, "barcode": f"89000000{i:04d}",
            "costPrice": float(cost), "sellPrice": float(sell), "stockQty": 0,
            "reorderLevel": int(max(4, round(base * 3))), "supplierId": sup,
            "_base": base, "_lt": lt, "_prof": prof,
            # owner's historical fixed order quantity: ~12 days of average demand
            "_orderQty": int(max(6, round(base * 12))),
            # popularity drift: slow trend per product
            "_trend": rng.normal(0.12, 0.08),
        })

    db = {
        "settings": {"shopName": "City Wine Store", "currency": "₹", "lowStockDefault": 6,
                     "cashInHand": 0, "bankBalance": 0,
                     "telegramBotToken": "", "telegramChatId": "", "telegramEnabled": False,
                     "lastTgSend2pm": "", "lastTgSend9pm": "",
                     "gdriveClientId": "", "gdriveEnabled": False, "gdriveFileId": "",
                     "appPin": "", "firebaseConfigJson": "", "syncEnabled": False},
        "categories": CATEGORIES[:], "expenseCategories": EXPENSE_CATEGORIES[:],
        "products": [], "suppliers": [dict(s) for s in SUPPLIERS],
        "purchases": [], "sales": [], "stockLedger": [], "expenses": [], "payments": [],
        "counters": {k: 0 for k in ["product", "supplier", "purchase", "sale", "ledger", "expense",
                                    "payment", "invoicePurchase", "invoiceSale"]},
    }
    C = db["counters"]

    def nid(kind):
        C[kind] += 1
        return C[kind]

    def ledger(d_iso, p, typ, qty, ref, notes=""):
        db["stockLedger"].append({"id": nid("ledger"), "date": d_iso, "productId": p["id"], "productName": p["name"],
                                  "type": typ, "qtyChange": int(qty), "balanceAfter": int(p["stockQty"]),
                                  "reference": ref, "notes": notes})
        return db["stockLedger"][-1]

    # Opening stock
    for p in products:
        p["stockQty"] = int(p["_orderQty"] * 1.5)
        ledger(_iso(WORLD_START, 3, 0), p, "Opening Stock", p["stockQty"], "SEED", "Opening stock")
    C["product"] = len(products)
    C["supplier"] = len(SUPPLIERS)

    # Pre-chosen anomaly plant dates (deterministic). Restricted to non-festival, non-dry days.
    normal_days = [i for i, d in enumerate(days) if d.isoformat() not in FESTIVALS and d.isoformat() not in DRY_DAYS
                   and i > 30]
    plant_rng = np.random.default_rng(seed + 1)
    spike_days = set(plant_rng.choice(normal_days, 10, replace=False).tolist())
    drop_days = set(plant_rng.choice([i for i in normal_days if i not in spike_days], 10, replace=False).tolist())
    dup_days = set(plant_rng.choice(normal_days, 14, replace=False).tolist())
    nameless_days = set(plant_rng.choice(normal_days, 12, replace=False).tolist())
    corrupt_days = set(plant_rng.choice(normal_days, 14, replace=False).tolist())
    cat_for_day = {i: CATEGORIES[int(plant_rng.integers(0, 7))] for i in spike_days | drop_days}
    sale_at_zero_budget = 14

    anomalies = {"duplicate_sale": [], "ledger_balance_mismatch": [], "sale_at_zero_stock": [],
                 "credit_sale_no_name": [], "demand_spike": [], "demand_drop": [], "shrinkage": []}

    pending = []  # (arrival_day_idx, product, qty, invoiceNo)
    latent_rows = []
    customers = ["Rakesh Das", "Bipul Kalita", "Manoj Sharma", "Dipankar Bora", "Anil Deka"]
    credit_outstanding = {c: 0.0 for c in customers}
    supplier_due = {s["id"]: 0.0 for s in SUPPLIERS}

    for di, d in enumerate(days):
        ds = d.isoformat()
        # 1) deliveries arrive in the morning
        for item in [x for x in pending if x[0] == di]:
            _, p, q, inv, credit = item
            p["stockQty"] += q
            total = q * p["costPrice"]
            paid = round(total * (0.5 if credit else 1.0), 2)
            supplier_due[p["supplierId"]] += total - paid
            db["purchases"].append({"id": nid("purchase"), "date": _iso(d, 5, 30), "invoiceNo": inv,
                                    "supplierId": p["supplierId"], "supplierName": SUPPLIERS[p["supplierId"] - 1]["name"],
                                    "productId": p["id"], "productName": p["name"], "qty": q, "costPrice": p["costPrice"],
                                    "total": total, "amountPaid": paid, "invoiceLink": ""})
            ledger(_iso(d, 5, 30), p, "Purchase", q, inv, "Purchase from " + SUPPLIERS[p["supplierId"] - 1]["name"])
        pending = [x for x in pending if x[0] != di]

        dry = ds in DRY_DAYS
        fest = FESTIVALS.get(ds, 1.0)
        t_years = di / 365.0
        dup_done = nameless_done = False

        for p in products:
            lam = (p["_base"] * DOW[d.weekday()] * (1.2 if is_payday(d) else 1.0) * fest
                   * month_factor(p["_prof"], d.month) * (1 + p["_trend"] * t_years))
            if di in spike_days and p["category"] == cat_for_day[di]:
                lam *= 3.0
            demand = 0 if dry else int(rng.negative_binomial(6, 6 / (6 + lam)))
            latent_rows.append({"date": ds, "productId": p["id"], "latent_demand": demand})
            if di in drop_days and p["category"] == cat_for_day[di]:
                demand = int(demand * 0.1)  # e.g. half-day closure / missed entries
            sold = min(demand, p["stockQty"])

            if sold > 0:
                # split into a cash day-total row and (sometimes) one credit row
                credit_q = 0
                if sold >= 3 and (rng.random() < 0.06 or (di in nameless_days and not nameless_done)):
                    credit_q = 1
                cash_q = sold - credit_q
                if cash_q > 0:
                    p["stockQty"] -= cash_q
                    inv = "SALE-%04d" % nid("invoiceSale")
                    tot = cash_q * p["sellPrice"]
                    sale = {"id": nid("sale"), "date": _iso(d, 14, 30), "invoiceNo": inv, "paymentMode": "Paid",
                            "customerName": "", "productId": p["id"], "productName": p["name"], "qty": cash_q,
                            "sellPrice": p["sellPrice"], "costPriceAtSale": p["costPrice"], "total": tot, "amountPaid": tot}
                    db["sales"].append(sale)
                    ledger(sale["date"], p, "Sale", -cash_q, inv, "Sold")
                    if di in dup_days and not dup_done:
                        dup = dict(sale, id=nid("sale"))  # double-submitted record, no ledger row
                        db["sales"].append(dup)
                        anomalies["duplicate_sale"].append(dup["id"])
                        dup_done = True
                if credit_q > 0:
                    p["stockQty"] -= credit_q
                    inv = "SALE-%04d" % nid("invoiceSale")
                    cust = customers[int(rng.integers(0, len(customers)))]
                    name = cust
                    if di in nameless_days and not nameless_done:
                        name = ""
                        nameless_done = True
                    tot = credit_q * p["sellPrice"]
                    sale = {"id": nid("sale"), "date": _iso(d, 15, 10), "invoiceNo": inv, "paymentMode": "Credit",
                            "customerName": name, "productId": p["id"], "productName": p["name"], "qty": credit_q,
                            "sellPrice": p["sellPrice"], "costPriceAtSale": p["costPrice"], "total": tot, "amountPaid": 0}
                    db["sales"].append(sale)
                    if name == "":
                        anomalies["credit_sale_no_name"].append(sale["id"])
                    else:
                        credit_outstanding[cust] += tot
                    ledger(sale["date"], p, "Sale", -credit_q, inv, "Sold (Credit: %s)" % name)

            # planted: sale recorded although stock is already zero (stock goes negative)
            if (p["stockQty"] == 0 and demand > sold and sale_at_zero_budget > 0 and not dry
                    and fest == 1.0 and rng.random() < 0.08):
                sale_at_zero_budget -= 1
                p["stockQty"] -= 1
                inv = "SALE-%04d" % nid("invoiceSale")
                sale = {"id": nid("sale"), "date": _iso(d, 15, 40), "invoiceNo": inv, "paymentMode": "Paid",
                        "customerName": "", "productId": p["id"], "productName": p["name"], "qty": 1,
                        "sellPrice": p["sellPrice"], "costPriceAtSale": p["costPrice"], "total": p["sellPrice"],
                        "amountPaid": p["sellPrice"]}
                db["sales"].append(sale)
                ledger(sale["date"], p, "Sale", -1, inv, "Sold")
                anomalies["sale_at_zero_stock"].append(sale["id"])
                # restock correction next morning so the negative is temporary
            # occasional breakage
            if p["stockQty"] > 5 and rng.random() < 0.004:
                p["stockQty"] -= 1
                kind, note = LOSS_KINDS[(di + p["id"]) % len(LOSS_KINDS)]
                ledger(_iso(d, 16, 0), p, "Loss: " + kind, -1, "LOSS", note)

            # owner's historical fixed-reorder rule
            on_order = sum(x[2] for x in pending if x[1] is p)
            if p["stockQty"] + on_order <= p["reorderLevel"]:
                lt = p["_lt"] + int(rng.integers(0, 2))
                inv = "PUR-%04d" % nid("invoicePurchase")
                q = p["_orderQty"] + max(0, -p["stockQty"])
                pending.append((di + lt, p, q, inv, bool(rng.random() < 0.25)))

        # planted latent-spike labels (recorded at category-day level)
        if di in spike_days:
            anomalies["demand_spike"].append({"date": ds, "category": cat_for_day[di]})
        if di in drop_days:
            anomalies["demand_drop"].append({"date": ds, "category": cat_for_day[di]})

        # corrupt a ledger row's balanceAfter (typo-style)
        if di in corrupt_days:
            todays = [r for r in db["stockLedger"] if r["date"].startswith(ds) and r["type"] == "Sale"]
            if todays:
                r = todays[int(rng.integers(0, len(todays)))]
                r["balanceAfter"] += int(rng.choice([-7, -5, -3, 3, 5, 8]))
                anomalies["ledger_balance_mismatch"].append(r["id"])

        # expenses
        if d.day == 1:
            for cat, amt, desc in [("Rent", 18000, "Shop rent"), ("Salary", 24000, "Staff salary (2)")]:
                db["expenses"].append({"id": nid("expense"), "date": ds, "category": cat, "description": desc, "amount": amt})
        if d.day == 10:
            db["expenses"].append({"id": nid("expense"), "date": ds, "category": "Electricity",
                                   "description": "Electricity bill", "amount": float(round(rng.normal(3200, 400)))})
        if d.weekday() == 0:
            db["expenses"].append({"id": nid("expense"), "date": ds, "category": "Transport",
                                   "description": "Delivery transport", "amount": float(round(rng.normal(900, 150)))})
        # payments: customers settle weekly, supplier dues fortnightly
        if d.weekday() == 6:
            for cust, due in credit_outstanding.items():
                if due > 0:
                    db["payments"].append({"id": nid("payment"), "date": _iso(d, 13, 0), "type": "CustomerPayment",
                                           "partyName": cust, "amount": round(due, 2), "notes": "Credit settled"})
                    credit_outstanding[cust] = 0.0
        if d.day in (1, 15):
            for sid, due in supplier_due.items():
                if due > 0:
                    db["payments"].append({"id": nid("payment"), "date": _iso(d, 6, 0), "type": "SupplierPayment",
                                           "partyName": SUPPLIERS[sid - 1]["name"], "amount": round(due, 2),
                                           "notes": "Payment against invoices"})
                    supplier_due[sid] = 0.0

    for p in products:
        clean = {k: v for k, v in p.items() if not k.startswith("_")}
        db["products"].append(clean)
    latent = pd.DataFrame(latent_rows)
    meta = {p["id"]: {"lead_time": p["_lt"], "order_qty": p["_orderQty"]} for p in products}
    db["_meta"] = meta  # stripped on export
    return World(db=db, latent=latent, anomalies=anomalies)


SHRINKAGE = {3: -4, 9: -6, 15: -9}  # productId -> unrecorded loss applied to recorded stockQty at as_of


def export(world: World, as_of: str, out_root: Path = ROOT / "data") -> dict:
    """Slice the world to records on/before as_of; set product stockQty from the ledger."""
    cutoff = as_of + "T23:59:59.999Z"
    src = world.db
    db = {k: (json.loads(json.dumps(v)) if not isinstance(v, list) else None) for k, v in src.items() if k != "_meta"}
    for k in ["purchases", "sales", "stockLedger", "expenses", "payments"]:
        db[k] = [dict(r) for r in src[k] if str(r["date"]) <= cutoff]
    db["products"] = [dict(p) for p in src["products"]]
    db["suppliers"] = [dict(s) for s in src["suppliers"]]
    db["categories"] = list(src["categories"])
    db["expenseCategories"] = list(src["expenseCategories"])
    # stockQty := ledger balance at as_of (last balanceAfter is unreliable if corrupted -> use cumulative sum)
    led = pd.DataFrame(db["stockLedger"])
    bal = led.groupby("productId")["qtyChange"].sum().to_dict()
    for p in db["products"]:
        p["stockQty"] = max(0, int(bal.get(p["id"], 0)) + SHRINKAGE.get(p["id"], 0))
    # counters consistent with exported ids
    mx = lambda arr: max([int(r["id"]) for r in arr], default=0)  # noqa: E731
    db["counters"] = {"product": mx(db["products"]), "supplier": mx(db["suppliers"]), "purchase": mx(db["purchases"]),
                      "sale": mx(db["sales"]), "ledger": mx(db["stockLedger"]), "expense": mx(db["expenses"]),
                      "payment": mx(db["payments"]),
                      "invoicePurchase": len({r["invoiceNo"] for r in db["purchases"]}),
                      "invoiceSale": len(db["sales"])}

    sale_ids = {r["id"] for r in db["sales"]}
    led_ids = {r["id"] for r in db["stockLedger"]}
    a = world.anomalies
    labels = {
        "as_of": as_of,
        "duplicate_sale": [i for i in a["duplicate_sale"] if i in sale_ids],
        "credit_sale_no_name": [i for i in a["credit_sale_no_name"] if i in sale_ids],
        "sale_at_zero_stock": [i for i in a["sale_at_zero_stock"] if i in sale_ids],
        "ledger_balance_mismatch": [i for i in a["ledger_balance_mismatch"] if i in led_ids],
        "demand_spike": [x for x in a["demand_spike"] if x["date"] <= as_of],
        "demand_drop": [x for x in a["demand_drop"] if x["date"] <= as_of],
        "shrinkage": sorted(p["id"] for p in db["products"] if p["stockQty"] != int(bal.get(p["id"], 0))),
    }
    raw = out_root / "raw"
    truth = out_root / "truth"
    raw.mkdir(parents=True, exist_ok=True)
    truth.mkdir(parents=True, exist_ok=True)
    (raw / f"db_{as_of}.json").write_text(json.dumps(db))
    write_xlsx(db, raw / f"db_{as_of}.xlsx")
    world.latent.to_parquet(truth / "latent_demand.parquet", index=False)
    (truth / "planted_anomalies.json").write_text(json.dumps(labels, indent=1))
    (truth / "product_meta.json").write_text(json.dumps(src["_meta"]))
    return db


def write_xlsx(db: dict, path: Path) -> None:
    """Same sheet names/columns as the app's buildWorkbook(), so importFromExcel() reads it."""
    settings = dict(db["settings"])
    settings["categories"] = ",".join(db["categories"])
    settings["expenseCategories"] = ",".join(db["expenseCategories"])
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for sheet, key in [("Products", "products"), ("Suppliers", "suppliers"), ("Purchases", "purchases"),
                           ("Sales", "sales"), ("StockLedger", "stockLedger"), ("Expenses", "expenses"),
                           ("Payments", "payments")]:
            pd.DataFrame(db[key]).to_excel(xw, sheet_name=sheet, index=False)
        pd.DataFrame([settings]).to_excel(xw, sheet_name="Settings", index=False)
        pd.DataFrame([db["counters"]]).to_excel(xw, sheet_name="Counters", index=False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=DEFAULT_AS_OF)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)
    world = simulate_world(args.seed)
    db = export(world, args.as_of)
    print(f"as_of={args.as_of} products={len(db['products'])} sales={len(db['sales'])} "
          f"ledger={len(db['stockLedger'])} purchases={len(db['purchases'])}")


if __name__ == "__main__":
    main()
