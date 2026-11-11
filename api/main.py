"""SelfSense API — serves the pipeline's published results.

It reads the same artifacts the static Insights tab reads (app/forecasts.json,
reports/*.json, models/registry.json). The demo web app does NOT depend on this
service; it is an additional, documented way to get the same results.
All data is SYNTHETIC.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

ROOT = Path(os.environ.get("SELFSENSE_ROOT", Path(__file__).resolve().parents[1]))
FILES = {
    "forecasts": ROOT / "app" / "forecasts.json",
    "quality": ROOT / "reports" / "quality.json",
    "registry": ROOT / "models" / "registry.json",
    "backtest": ROOT / "reports" / "backtest.json",
}
log = logging.getLogger("selfsense.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
_cache: dict[str, tuple[float, dict]] = {}


def load(name: str) -> dict:
    """Read a JSON artifact, re-reading only when the file changed (mtime cache)."""
    p = FILES[name]
    if not p.exists():
        raise HTTPException(503, f"{p.name} not published yet — run `python -m mlops.retrain`")
    m = p.stat().st_mtime
    if name not in _cache or _cache[name][0] != m:
        _cache[name] = (m, json.loads(p.read_text()))
    return _cache[name][1]


app = FastAPI(title="SelfSense API", version="0.1.0",
              description="Forecasts, reorder suggestions and data-quality results (synthetic demo data).")


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    resp.headers["X-Process-Time-ms"] = f"{ms:.1f}"
    log.info("%s %s %s %.1fms", request.method, request.url.path, resp.status_code, ms)
    return resp


class ForecastRequest(BaseModel):
    product_ids: list[int] = Field(default_factory=list, description="empty = all products")
    horizon: int = Field(14, ge=1, le=14)


@app.get("/health")
def health():
    f = load("forecasts")
    return {"status": "ok", "model_version": f["meta"]["model_version"], "data_as_of": f["meta"]["as_of"],
            "data": "SYNTHETIC"}


@app.post("/forecast")
def forecast(req: ForecastRequest):
    f = load("forecasts")
    prods = f["products"]
    if req.product_ids:
        known = {p["productId"] for p in prods}
        missing = sorted(set(req.product_ids) - known)
        if missing:
            raise HTTPException(404, f"unknown product ids: {missing}")
        prods = [p for p in prods if p["productId"] in set(req.product_ids)]
    out = []
    for p in prods:
        fc = p["forecast"]
        k = req.horizon
        out.append({"productId": p["productId"], "name": p["name"], "category": p["category"], "model": p["model"],
                    "dates": fc["dates"][:k], "yhat": fc["yhat"][:k], "lo_80": fc["lo"][:k], "hi_80": fc["hi"][:k]})
    return {"model_version": f["meta"]["model_version"], "as_of": f["meta"]["as_of"], "horizon": req.horizon,
            "note": "served from the latest published forecast run (precomputed), not re-fitted per request",
            "forecasts": out}


@app.get("/reorder-suggestions")
def reorder_suggestions(supplier_id: int | None = None, only_needed: bool = True):
    f = load("forecasts")
    rows = f["reorder_suggestions"]
    if supplier_id is not None:
        rows = [r for r in rows if r["supplierId"] == supplier_id]
    if only_needed:
        rows = [r for r in rows if r["suggested_qty"] > 0]
    return {"as_of": f["meta"]["as_of"], "service_level": 0.95, "count": len(rows), "suggestions": rows}


@app.get("/quality-report")
def quality_report():
    return load("quality")


@app.get("/model-info")
def model_info():
    f, reg = load("forecasts"), load("registry")
    prod = next((v for v in reg["versions"] if v["version"] == reg["production"]), None)
    return {"production": prod, "model_info": f["model_info"], "registry_size": len(reg["versions"]),
            "promotion_threshold": reg["promotion_threshold"], "monitoring": f["monitoring"]}
