"""Extract -> Transform -> Validate -> Load for the shop's DB export.

Extract : read the DB object from the app's JSON or .xlsx export.
Transform: build an analysis-ready daily table per product (and per category),
           with stock REBUILT from the event-sourced stockLedger (not stockQty).
Validate: schema + basic integrity checks (hard failures) — the anomaly-style
          data-quality checks live in quality/checks.py.
Load    : write Parquet files + a DuckDB database; category aggregates use SQL.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from pipeline.calendar_config import DRY_DAYS, FESTIVALS, HOLIDAYS

ROOT = Path(__file__).resolve().parents[1]
TABLES = ["products", "suppliers", "purchases", "sales", "stockLedger", "expenses", "payments"]

REQUIRED = {
    "products": ["id", "name", "brand", "category", "barcode", "costPrice", "sellPrice", "stockQty", "reorderLevel",
                 "supplierId"],
    "suppliers": ["id", "name"],
    "purchases": ["id", "date", "invoiceNo", "supplierId", "productId", "productName", "qty", "costPrice", "total", "amountPaid"],
    "sales": ["id", "date", "invoiceNo", "paymentMode", "customerName", "productId", "productName", "qty", "sellPrice",
              "costPriceAtSale", "total", "amountPaid"],
    "stockLedger": ["id", "date", "productId", "productName", "type", "qtyChange", "balanceAfter", "reference"],
    "expenses": ["id", "date", "category", "amount"],
    "payments": ["id", "date", "type", "partyName", "amount"],
}
SHEETS = {"products": "Products", "suppliers": "Suppliers", "purchases": "Purchases", "sales": "Sales",
          "stockLedger": "StockLedger", "expenses": "Expenses", "payments": "Payments"}


# ----------------------------------------------------------------- extract
def extract(path: str | Path) -> dict[str, pd.DataFrame]:
    path = Path(path)
    if path.suffix == ".json":
        db = json.loads(path.read_text())
        return {t: pd.DataFrame(db.get(t, [])) for t in TABLES}
    if path.suffix in (".xlsx", ".xls"):
        xl = pd.read_excel(path, sheet_name=None)
        return {t: xl.get(SHEETS[t], pd.DataFrame()) for t in TABLES}
    raise ValueError(f"unsupported file: {path}")


# ---------------------------------------------------------------- validate
class ValidationError(Exception):
    pass


def validate(tables: dict[str, pd.DataFrame]) -> dict:
    """Hard schema checks. Raises ValidationError on structural problems."""
    errors, warnings = [], []
    for t, cols in REQUIRED.items():
        df = tables.get(t)
        if df is None:
            errors.append(f"{t}: table missing")
            continue
        missing = [c for c in cols if c not in df.columns]
        if missing and len(df):
            errors.append(f"{t}: missing columns {missing}")
        if "id" in df.columns and df["id"].duplicated().any():
            errors.append(f"{t}: duplicate ids")
        if "date" in df.columns and len(df):
            bad = pd.to_datetime(df["date"], errors="coerce", utc=True).isna().sum()
            if bad:
                errors.append(f"{t}: {bad} unparseable dates")
    s = tables["sales"]
    if len(s) and not errors:
        if (s["qty"] <= 0).any():
            errors.append("sales: non-positive qty")
        mism = (np.abs(s["qty"] * s["sellPrice"] - s["total"]) > 0.01).sum()
        if mism:
            warnings.append(f"sales: {mism} rows where qty*sellPrice != total")
        unknown = ~s["productId"].isin(tables["products"]["id"])
        if unknown.any():
            errors.append(f"sales: {unknown.sum()} rows reference unknown products")
    report = {"errors": errors, "warnings": warnings,
              "row_counts": {t: int(len(df)) for t, df in tables.items()}}
    if errors:
        raise ValidationError("; ".join(errors))
    return report


# --------------------------------------------------------------- transform
def _local_date(series: pd.Series) -> pd.Series:
    """App stores UTC ISO timestamps; the shop operates in IST (UTC+5:30)."""
    ts = pd.to_datetime(series, utc=True) + pd.Timedelta(hours=5, minutes=30)
    return ts.dt.strftime("%Y-%m-%d")


def dedupe_sales(sales: pd.DataFrame) -> pd.DataFrame:
    """Drop double-submitted rows (same invoiceNo + product + qty + timestamp)."""
    return sales.drop_duplicates(subset=["invoiceNo", "productId", "qty", "date"], keep="first")


def calendar_features(dates: pd.Series) -> pd.DataFrame:
    d = pd.to_datetime(dates)
    return pd.DataFrame({
        "dow": d.dt.dayofweek, "month": d.dt.month, "dom": d.dt.day,
        "is_weekend": (d.dt.dayofweek >= 5).astype(int),
        "is_payday": (d.dt.day <= 5).astype(int),
        "festival_mult": dates.map(lambda x: FESTIVALS.get(x, 1.0)),
        "is_festival": dates.isin(list(FESTIVALS)).astype(int),
        "is_dry_day": dates.isin(list(DRY_DAYS)).astype(int),
        "is_holiday": dates.isin(list(HOLIDAYS)).astype(int),
    })


def transform(tables: dict[str, pd.DataFrame], as_of: str | None = None) -> dict[str, pd.DataFrame]:
    products = tables["products"]
    sales = dedupe_sales(tables["sales"]).copy()
    led = tables["stockLedger"].copy()
    sales["day"] = _local_date(sales["date"])
    led["day"] = _local_date(led["date"])

    start = min(led["day"].min(), sales["day"].min())
    end = as_of or max(led["day"].max(), sales["day"].max())
    days = pd.date_range(start, end, freq="D").strftime("%Y-%m-%d")
    grid = pd.MultiIndex.from_product([products["id"].tolist(), days], names=["productId", "date"]).to_frame(index=False)

    units = sales.groupby(["productId", "day"]).agg(units=("qty", "sum"), revenue=("total", "sum")).reset_index()
    units = units.rename(columns={"day": "date"})
    # Rebuild stock from the event-sourced ledger: closing stock = cumulative sum of qtyChange
    lday = led.groupby(["productId", "day"])["qtyChange"].sum().reset_index().rename(columns={"day": "date"})

    df = grid.merge(units, on=["productId", "date"], how="left").merge(lday, on=["productId", "date"], how="left")
    df[["units", "revenue", "qtyChange"]] = df[["units", "revenue", "qtyChange"]].fillna(0)
    df = df.sort_values(["productId", "date"])
    df["closing_stock"] = df.groupby("productId")["qtyChange"].cumsum()
    df["opening_stock"] = df["closing_stock"] - df["qtyChange"]
    df["stockout"] = (df["closing_stock"] <= 0).astype(int)
    df = df.merge(products[["id", "name", "category"]].rename(columns={"id": "productId"}), on="productId")
    cal = calendar_features(df["date"]).set_index(df.index)
    df = pd.concat([df, cal], axis=1)
    df["units"] = df["units"].astype(int)
    product_daily = df.drop(columns=["qtyChange"]).reset_index(drop=True)
    return {"product_daily": product_daily}


# -------------------------------------------------------------------- load
def load(out: dict[str, pd.DataFrame], out_dir: Path = ROOT / "data" / "processed") -> dict[str, pd.DataFrame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdaily = out["product_daily"]
    pdaily.to_parquet(out_dir / "product_daily.parquet", index=False)
    con = duckdb.connect(str(out_dir / "shop.duckdb"))
    con.execute("CREATE OR REPLACE TABLE product_daily AS SELECT * FROM pdaily")
    # Category-level daily table via SQL. A category is "stocked out" on a day if
    # any of its products closed at zero stock (demand is then partly censored).
    con.execute("""
        CREATE OR REPLACE TABLE category_daily AS
        SELECT category, date,
               SUM(units)::INT        AS units,
               SUM(revenue)           AS revenue,
               SUM(closing_stock)::INT AS closing_stock,
               MAX(stockout)          AS stockout,
               ANY_VALUE(dow) AS dow, ANY_VALUE(month) AS month, ANY_VALUE(dom) AS dom,
               ANY_VALUE(is_weekend) AS is_weekend, ANY_VALUE(is_payday) AS is_payday,
               ANY_VALUE(festival_mult) AS festival_mult, ANY_VALUE(is_festival) AS is_festival,
               ANY_VALUE(is_dry_day) AS is_dry_day, ANY_VALUE(is_holiday) AS is_holiday
        FROM product_daily GROUP BY category, date ORDER BY category, date
    """)
    cdaily = con.execute("SELECT * FROM category_daily").df()
    con.close()
    cdaily.to_parquet(out_dir / "category_daily.parquet", index=False)
    out["category_daily"] = cdaily
    return out


def run(path: str | Path, as_of: str | None = None, out_dir: Path = ROOT / "data" / "processed") -> dict:
    tables = extract(path)
    report = validate(tables)
    out = load(transform(tables, as_of), out_dir)
    report["product_daily_rows"] = int(len(out["product_daily"]))
    report["category_daily_rows"] = int(len(out["category_daily"]))
    report["date_range"] = [out["product_daily"]["date"].min(), out["product_daily"]["date"].max()]
    (out_dir / "validation_report.json").write_text(json.dumps(report, indent=1))
    return {"tables": tables, "report": report, **out}


if __name__ == "__main__":
    import sys
    as_of = sys.argv[1] if len(sys.argv) > 1 else "2026-09-30"
    res = run(ROOT / "data" / "raw" / f"db_{as_of}.json", as_of)
    print(json.dumps(res["report"], indent=1))

