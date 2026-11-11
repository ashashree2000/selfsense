from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "app" / "forecasts.json").exists(), reason="no published forecasts")


@pytest.fixture(scope="module")
def client():
    from api.main import app
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["data"] == "SYNTHETIC"
    assert "X-Process-Time-ms" in r.headers


def test_forecast_subset_and_horizon(client):
    r = client.post("/forecast", json={"product_ids": [1, 2], "horizon": 7})
    assert r.status_code == 200
    body = r.json()
    assert [f["productId"] for f in body["forecasts"]] == [1, 2]
    assert all(len(f["yhat"]) == 7 and all(lo <= hi for lo, hi in zip(f["lo_80"], f["hi_80"])) for f in body["forecasts"])


def test_forecast_validation(client):
    assert client.post("/forecast", json={"horizon": 30}).status_code == 422
    assert client.post("/forecast", json={"product_ids": [9999]}).status_code == 404


def test_other_endpoints(client):
    assert client.get("/reorder-suggestions").status_code == 200
    assert "scores" in client.get("/quality-report").json()
    mi = client.get("/model-info").json()
    assert mi["production"]["version"] == mi["model_info"]["version"]
