"""Four forecasters, simple -> complex, all with the same interface:

    forecast(name, hist, origin, horizon) -> DataFrame[productId, date, h, yhat]

`hist` is the product_daily table restricted to dates <= origin (the caller
guarantees no future rows; the functions also re-filter defensively).
A "valid" day is one that is neither a stock-out (demand censored) nor a dry
day (shop closed); invalid days are skipped when estimating levels.
All models output 0 on known dry days (a calendar rule shared by every model).
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from pipeline.etl import calendar_features

LAST_GBM: dict | None = None  # most recently fitted GBM (saved as a versioned artifact)
MODEL_NAMES = ["seasonal_naive", "moving_average", "holt_winters", "gbm"]
HGB_PARAMS = dict(loss="poisson", learning_rate=0.05, max_iter=300, max_leaf_nodes=31,
                  min_samples_leaf=20, l2_regularization=1.0, random_state=0)


def _future_dates(origin: str, horizon: int) -> list[str]:
    o = pd.Timestamp(origin)
    return [(o + pd.Timedelta(days=h)).strftime("%Y-%m-%d") for h in range(1, horizon + 1)]


def _matrices(hist: pd.DataFrame, origin: str):
    h = hist[hist["date"] <= origin]
    y = h.pivot(index="date", columns="productId", values="units").sort_index()
    valid = ~(h.pivot(index="date", columns="productId", values="stockout").astype(bool)
              | h.pivot(index="date", columns="productId", values="is_dry_day").astype(bool))
    valid = valid.reindex_like(y).fillna(False)
    return y, valid


def _apply_dry(out: pd.DataFrame) -> pd.DataFrame:
    dry = calendar_features(out["date"])["is_dry_day"].to_numpy() == 1
    out.loc[dry, "yhat"] = 0.0
    out["yhat"] = out["yhat"].clip(lower=0)
    return out


def _frame(per_product: dict[int, np.ndarray], dates: list[str]) -> pd.DataFrame:
    rows = []
    for pid, vals in per_product.items():
        for i, (d, v) in enumerate(zip(dates, vals)):
            rows.append((pid, d, i + 1, float(v)))
    return pd.DataFrame(rows, columns=["productId", "date", "h", "yhat"])


def seasonal_naive(hist, origin, horizon):
    """Same weekday last week (skipping back further weeks if that day was censored/closed)."""
    y, valid = _matrices(hist, origin)
    dates = _future_dates(origin, horizon)
    out = {}
    for pid in y.columns:
        yy, vv = y[pid].to_numpy(float), valid[pid].to_numpy(bool)
        n = len(yy)
        fallback = yy[vv][-28:].mean() if vv.any() else 0.0
        vals = []
        for h in range(1, horizon + 1):
            idx = n - 1 + h - 7 * int(np.ceil(h / 7))
            while idx >= 0 and not vv[idx]:
                idx -= 7
            vals.append(yy[idx] if idx >= 0 else fallback)
        out[pid] = np.array(vals)
    return _apply_dry(_frame(out, dates))


def moving_average(hist, origin, horizon, window: int = 28):
    """Flat forecast = mean of valid days in the last `window` days."""
    y, valid = _matrices(hist, origin)
    dates = _future_dates(origin, horizon)
    out = {}
    for pid in y.columns:
        yy, vv = y[pid].to_numpy(float)[-window:], valid[pid].to_numpy(bool)[-window:]
        m = yy[vv].mean() if vv.any() else 0.0
        out[pid] = np.full(horizon, m)
    return _apply_dry(_frame(out, dates))


def holt_winters(hist, origin, horizon, window: int = 182):
    """Additive damped-trend Holt-Winters with weekly seasonality (statsmodels)."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    y, valid = _matrices(hist, origin)
    dates = _future_dates(origin, horizon)
    out = {}
    for pid in y.columns:
        s = y[pid].iloc[-window:].astype(float).copy()
        v = valid[pid].iloc[-window:]
        # impute censored/closed days with the same-weekday median of valid days
        dow = pd.to_datetime(s.index).dayofweek
        med = s[v.values].groupby(dow[v.values]).median()
        s[~v.values] = [med.get(d, s[v.values].mean()) for d in dow[~v.values]]
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fit = ExponentialSmoothing(s.to_numpy(), trend="add", damped_trend=True, seasonal="add",
                                           seasonal_periods=7, initialization_method="estimated").fit()
            out[pid] = np.asarray(fit.forecast(horizon))
        except Exception:  # pragma: no cover - fallback keeps the pipeline running
            out[pid] = np.full(horizon, s.iloc[-28:].mean())
    return _apply_dry(_frame(out, dates))


# ------------------------------------------------------------------ GBM
FEATURES = ["pid", "cat", "h", "dow", "dom", "month", "is_weekend", "is_payday", "is_festival",
            "is_holiday", "m7", "m28", "sdow4"]


def _level_stats(y: pd.DataFrame, valid: pd.DataFrame):
    """Per date t (rows) and product (cols): rolling means over VALID days up to and including t."""
    ym = y.where(valid)
    m7 = ym.rolling(7, min_periods=1).mean()
    m28 = ym.rolling(28, min_periods=1).mean()
    # same-weekday mean of the last 4 occurrences (t, t-7, t-14, t-21)
    stack = np.stack([ym.shift(7 * k).to_numpy() for k in range(4)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sdow4 = pd.DataFrame(np.nanmean(stack, axis=0), index=y.index, columns=y.columns)
    fill = m28
    return m7.fillna(fill), m28, sdow4.fillna(fill)


def _samples(y, valid, cats, origin_positions, horizon, target_needed=True):
    m7, m28, sdow4 = _level_stats(y, valid)
    dates = y.index.to_list()
    n = len(dates)
    rows = []
    for io in origin_positions:
        o = pd.Timestamp(dates[io])
        for h in range(1, horizon + 1):
            it = io + h
            tdate = (o + pd.Timedelta(days=h)).strftime("%Y-%m-%d")
            if target_needed and it >= n:
                break
            src = io + h - 7 * int(np.ceil(h / 7))  # latest same-weekday date <= origin
            for j, pid in enumerate(y.columns):
                if target_needed and not valid.iat[it, j]:
                    continue
                rows.append({"pid": int(pid), "cat": cats[pid], "h": h, "date": tdate,
                             "m7": m7.iat[io, j], "m28": m28.iat[io, j],
                             "sdow4": sdow4.iat[src, j] if src >= 0 else m28.iat[io, j],
                             "y": float(y.iat[it, j]) if target_needed else np.nan})
    df = pd.DataFrame(rows)
    if len(df):
        cal = calendar_features(df["date"]).set_index(df.index)
        df = pd.concat([df, cal.drop(columns=["festival_mult"])], axis=1)
    return df


def gbm(hist, origin, horizon, train_stride: int = 3):
    """Global HistGradientBoosting (Poisson loss) direct multi-horizon model.

    Training rows are built from pseudo-origins inside the training period, with
    features computed only from data on/before each pseudo-origin, and targets on
    or before `origin` -> no look-ahead leakage.
    Note: only the festival FLAG is a feature, not the generator's multiplier.
    """
    y, valid = _matrices(hist, origin)
    prods = hist.drop_duplicates("productId").set_index("productId")["category"]
    cat_codes = {c: i for i, c in enumerate(sorted(prods.unique()))}
    cats = {pid: cat_codes[c] for pid, c in prods.items()}
    n = len(y)
    origins = list(range(56, n - 1, train_stride))
    train = _samples(y, valid, cats, origins, horizon, target_needed=True)
    model = HistGradientBoostingRegressor(categorical_features=[0, 1], **HGB_PARAMS)
    model.fit(train[FEATURES].to_numpy(float), train["y"].to_numpy(float))
    global LAST_GBM
    LAST_GBM = {"model": model, "features": FEATURES, "cat_codes": cat_codes, "origin": origin,
                "n_train_rows": int(len(train))}
    test = _samples(y, valid, cats, [n - 1], horizon, target_needed=False)
    test["yhat"] = model.predict(test[FEATURES].to_numpy(float))
    out = test.rename(columns={"pid": "productId"})[["productId", "date", "h", "yhat"]]
    return _apply_dry(out.reset_index(drop=True))


MODELS = {"seasonal_naive": seasonal_naive, "moving_average": moving_average,
          "holt_winters": holt_winters, "gbm": gbm}


def forecast(name: str, hist: pd.DataFrame, origin: str, horizon: int = 14) -> pd.DataFrame:
    return MODELS[name](hist[hist["date"] <= origin], origin, horizon)
