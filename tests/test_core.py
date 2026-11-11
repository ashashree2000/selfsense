import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from forecasting.backtest import HOLDOUT_DAYS, origins_for
from forecasting.metrics import bias, coverage, mase, seasonal_scale, wape
from forecasting.models import forecast
from inventory.reorder import policy_levels
from pipeline import etl
from pipeline.generate_data import export, simulate_world
from quality import checks

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def data(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    world = simulate_world()
    db = export(world, "2026-03-31", out_root=out)
    tables = {t: pd.DataFrame(db[t]) for t in etl.TABLES}
    res = etl.load(etl.transform(tables, "2026-03-31"), out / "processed")
    labels = json.loads((out / "truth" / "planted_anomalies.json").read_text())
    return {"db": db, "tables": tables, "labels": labels, "out": out, **res}


# ---------------------------------------------------------------- metrics
def test_metrics_basic():
    y, f = np.array([10, 0, 5]), np.array([8, 1, 5])
    assert wape(y, f) == pytest.approx(3 / 15)
    assert bias(y, f) == pytest.approx(-1 / 15)
    assert mase(y, f, scale=2.0) == pytest.approx(1 / 2)
    assert coverage(y, y - 1, y + 1) == 1.0
    assert seasonal_scale(np.arange(14.0), m=7) == pytest.approx(7.0)


def test_wape_zero_actuals_is_nan():
    assert np.isnan(wape([0, 0], [1, 2]))


# ------------------------------------------------------------- generator
def test_generator_schema_and_reproducible(data):
    db = data["db"]
    for key in ["settings", "categories", "products", "suppliers", "purchases", "sales", "stockLedger", "expenses",
                "payments", "counters"]:
        assert key in db
    assert set(db["sales"][0]) == set(etl.REQUIRED["sales"])
    assert db["settings"]["telegramBotToken"] == "" and db["settings"]["firebaseConfigJson"] == ""
    again = simulate_world()
    assert len(again.db["sales"]) == len(simulate_world().db["sales"])  # seeded


def test_validate_passes_and_detects_missing_column(data):
    rep = etl.validate(data["tables"])
    assert rep["errors"] == []
    broken = dict(data["tables"])
    broken["sales"] = broken["sales"].drop(columns=["qty"])
    with pytest.raises(etl.ValidationError):
        etl.validate(broken)


def test_stock_rebuilt_from_ledger(data):
    pdaily = data["product_daily"]
    led = data["tables"]["stockLedger"]
    final = pdaily.sort_values("date").groupby("productId")["closing_stock"].last()
    assert final.to_dict() == led.groupby("productId")["qtyChange"].sum().to_dict()


def test_calendar_features():
    cal = etl.calendar_features(pd.Series(["2026-01-14", "2026-01-26", "2026-02-07"]))
    assert cal["is_festival"].tolist() == [1, 0, 0]
    assert cal["is_dry_day"].tolist() == [0, 1, 0]
    assert cal["is_weekend"].tolist() == [0, 0, 1]


def test_dedupe_drops_planted_duplicates(data):
    s = data["tables"]["sales"]
    assert len(s) - len(etl.dedupe_sales(s)) == len(data["labels"]["duplicate_sale"])


# ---------------------------------------------------------------- models
@pytest.mark.parametrize("name", ["seasonal_naive", "moving_average", "holt_winters", "gbm"])
def test_models_shape_and_no_leakage(data, name):
    p = data["product_daily"]
    origin = "2026-02-28"
    f1 = forecast(name, p, origin, 14)
    assert len(f1) == p["productId"].nunique() * 14 and (f1["yhat"] >= 0).all()
    # tamper with the future: forecasts must not change
    p2 = p.copy()
    p2.loc[p2["date"] > origin, "units"] = 999
    f2 = forecast(name, p2, origin, 14)
    np.testing.assert_allclose(f1["yhat"].to_numpy(), f2["yhat"].to_numpy())


def test_dry_day_forecast_is_zero(data):
    f = forecast("moving_average", data["product_daily"], "2026-01-20", 14)
    assert (f.loc[f["date"] == "2026-01-26", "yhat"] == 0).all()


def test_backtest_origins_do_not_touch_holdout():
    bt, ho = origins_for("2026-10-31")
    hold_start = pd.Timestamp("2026-10-31") - pd.Timedelta(days=HOLDOUT_DAYS - 1)
    assert all(pd.Timestamp(o) + pd.Timedelta(days=14) < hold_start for o in bt)
    assert pd.Timestamp(ho[0]) == hold_start - pd.Timedelta(days=1)


# --------------------------------------------------------------- quality
def test_rule_checks_find_planted(data):
    res = checks.run_checks(data["tables"], data["category_daily"])
    scores = {s["check"]: s for s in checks.evaluate(res, data["labels"])}
    for c in ["duplicate_sale", "credit_sale_no_name", "ledger_balance_mismatch", "shrinkage"]:
        assert scores[c]["recall"] == 1.0, c


def test_credit_no_name_unit():
    s = pd.DataFrame([{"id": 1, "invoiceNo": "S1", "paymentMode": "Credit", "customerName": " ", "total": 10, "date": "x"},
                      {"id": 2, "invoiceNo": "S2", "paymentMode": "Credit", "customerName": "A", "total": 10, "date": "x"},
                      {"id": 3, "invoiceNo": "S3", "paymentMode": "Paid", "customerName": "", "total": 10, "date": "x"}])
    assert checks.credit_sale_no_name(s)[0] == [1]


def test_ledger_mismatch_unit():
    led = pd.DataFrame([{"id": 1, "productId": 1, "productName": "a", "date": "2026-01-01T01", "type": "Opening Stock",
                         "qtyChange": 5, "balanceAfter": 5, "reference": "SEED"},
                        {"id": 2, "productId": 1, "productName": "a", "date": "2026-01-02T01", "type": "Sale",
                         "qtyChange": -2, "balanceAfter": 9, "reference": "S1"},
                        {"id": 3, "productId": 1, "productName": "a", "date": "2026-01-03T01", "type": "Sale",
                         "qtyChange": -1, "balanceAfter": 2, "reference": "S2"}])
    assert checks.ledger_balance_mismatch(led)[0] == [2]


# --------------------------------------------------------------- reorder
def test_policy_levels():
    f = np.full(14, 2.0)
    rop, up_to = policy_levels(f, sigma=0.0, lead=2, service_level=0.95, cover_days=7)
    assert rop == pytest.approx(6.0) and up_to == pytest.approx(20.0)
    rop2, _ = policy_levels(f, sigma=1.0, lead=2, service_level=0.95, cover_days=7)
    assert rop2 > rop
