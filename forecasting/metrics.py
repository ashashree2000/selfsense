"""Forecast metrics. All take aligned arrays of actuals y and forecasts f."""
from __future__ import annotations

import numpy as np


def wape(y, f) -> float:
    """Weighted absolute percentage error: sum|y-f| / sum|y|."""
    y, f = np.asarray(y, float), np.asarray(f, float)
    denom = np.abs(y).sum()
    return float(np.abs(y - f).sum() / denom) if denom > 0 else float("nan")


def bias(y, f) -> float:
    """Signed: sum(f-y)/sum(y). Positive = over-forecasting."""
    y, f = np.asarray(y, float), np.asarray(f, float)
    denom = np.abs(y).sum()
    return float((f - y).sum() / denom) if denom > 0 else float("nan")


def mase(y, f, scale: float) -> float:
    """Mean absolute error scaled by the in-sample MAE of the weekly seasonal-naive forecast."""
    y, f = np.asarray(y, float), np.asarray(f, float)
    if scale is None or not np.isfinite(scale) or scale <= 0 or len(y) == 0:
        return float("nan")
    return float(np.abs(y - f).mean() / scale)


def seasonal_scale(train_y: np.ndarray, valid: np.ndarray | None = None, m: int = 7) -> float:
    """In-sample MAE of y_t vs y_{t-m}, using only pairs where both days are valid."""
    y = np.asarray(train_y, float)
    v = np.ones(len(y), bool) if valid is None else np.asarray(valid, bool)
    if len(y) <= m:
        return float("nan")
    d = np.abs(y[m:] - y[:-m])
    ok = v[m:] & v[:-m]
    return float(d[ok].mean()) if ok.any() else float("nan")


def coverage(y, lo, hi) -> float:
    y, lo, hi = (np.asarray(a, float) for a in (y, lo, hi))
    return float(((y >= lo) & (y <= hi)).mean()) if len(y) else float("nan")
