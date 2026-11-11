# SelfSense — Retail POS + Forecasting Demo

> **This is a separate public demo.** It is a copy of a single-file retail POS app I built for a family-run shop, with a
> production-style ML layer added on top. **All data here is synthetic** (seeded generator, fictional brands and
> suppliers). The production app, its repository, deployment, cloud accounts and real data are **private and unchanged**.
> In this copy, Telegram, Google Drive and Firebase sync are hard-disabled.

**Problem.** Small retail shops reorder by gut feel and a fixed "low stock" number, so they run out during demand
spikes (festivals, paydays, weekends) and overstock in quiet weeks.
**What this adds.** A data pipeline, demand forecasting with honest backtesting, data-quality checks, a reorder policy
and simulation, an API, CI, and scheduled retraining with model versioning and monitoring. The results show up in a
new **Insights** tab inside the existing app.

- Live demo: _Vercel URL (see deployment section)_
- Stack: Python (pandas, NumPy, scikit-learn, statsmodels, SciPy, DuckDB, PyArrow), FastAPI, Docker, GitHub Actions, Playwright, vanilla JS (existing app)

## Architecture

```mermaid
flowchart LR
  subgraph App["Existing app (single index.html, no backend)"]
    UI[Sell / Stock / Purchase / Accounts ...]
    INS["Insights tab (new, insights.js)"]
  end
  GEN["pipeline/generate_data.py<br/>seeded synthetic DB<br/>(app's exact schema)"] -->|db.json / db.xlsx| ETL
  ETL["pipeline/etl.py<br/>extract → validate → transform<br/>stock rebuilt from stockLedger<br/>Parquet + DuckDB"] --> Q["quality/checks.py<br/>DQ + anomaly checks"]
  ETL --> BT["forecasting/<br/>4 models · rolling-origin backtest<br/>holdout · conformal intervals"]
  BT --> REG["models/registry.json<br/>versioned artifacts<br/>champion / challenger"]
  BT --> INV["inventory/reorder.py<br/>reorder points + simulation"]
  REG --> PUB["app/forecasts.json<br/>(static, published)"]
  Q --> PUB
  INV --> PUB
  MON["monitoring<br/>live accuracy + drift"] --> PUB
  PUB --> INS
  PUB --> API["api/ FastAPI (Docker)<br/>/forecast /reorder-suggestions<br/>/quality-report /model-info"]
  GEN -. demo_db.json .-> UI
  GHA["GitHub Actions<br/>CI + weekly retrain"] --> GEN
  GHA -->|commit| PUB
  PUB -->|push → redeploy| VERCEL[(Vercel static site)]
```

## Results

<!-- RESULTS:START -->
_Auto-generated from `reports/*.json` by `mlops/update_readme.py`. Data as of **2026-10-31**. All data is SYNTHETIC._

### Forecast accuracy — holdout (last 28 days, never used for model selection)

Product-level daily forecasts, 14-day horizon. Stock-out and dry days excluded from scoring.

| Model | WAPE | vs seasonal naive | MASE | Bias | 80% interval coverage |
|---|---|---|---|---|---|
| seasonal_naive | 67.4% | +0.0% | 1.079 | -4.9% | 81.4% |
| moving_average | 53.6% | -20.4% | 0.873 | -12.2% | 76.6% |
| holt_winters | 49.7% | -26.2% | 0.809 | -10.5% | 80.7% |
| gbm | 49.2% | -26.9% | 0.796 | -16.1% | 81.2% |
| selected_per_category | 49.3% | -26.9% | 0.797 | -14.8% | 80.9% |

Rolling-origin backtest (20 origins, 2025-12-27 → 2026-09-19): seasonal_naive WAPE 66.8%, moving_average WAPE 52.5%, holt_winters WAPE 50.5%, gbm WAPE 50.2%, selected_per_category WAPE 50.0%.

Model selected per category (by backtest WAPE): 150ml → gbm, 180ml → gbm, 375ml → gbm, 750ml → gbm, 90ml → holt_winters, Beer → gbm, Wine → gbm.

**Festival days** (WAPE / bias):

| Model | Backtest windows | Holdout |
|---|---|---|
| seasonal_naive | 59.8% / -45.6% (n=96) | 56.2% / -52.4% (n=36) |
| moving_average | 51.9% / -38.5% (n=96) | 55.6% / -55.4% (n=36) |
| holt_winters | 57.6% / -47.6% (n=96) | 52.0% / -50.2% (n=36) |
| gbm | 49.9% / -25.1% (n=96) | 44.6% / -33.1% (n=36) |
| selected_per_category | 53.6% / -34.7% (n=96) | 44.4% / -37.6% (n=36) |

### Data-quality checks vs planted anomalies

| Check | Planted | Flagged | Precision | Recall |
|---|---|---|---|---|
| duplicate_sale | 7 | 7 | 100.0% | 100.0% |
| credit_sale_no_name | 10 | 10 | 100.0% | 100.0% |
| sale_at_zero_stock | 14 | 14 | 100.0% | 100.0% |
| ledger_balance_mismatch | 10 | 10 | 100.0% | 100.0% |
| shrinkage | 3 | 3 | 100.0% | 100.0% |
| demand_spike | 9 | 15 | 26.7% | 44.4% |
| demand_drop | 6 | 6 | 16.7% | 16.7% |

The five rule-based checks are exact by construction on this synthetic data (each rule mirrors how the anomaly was planted). The statistical spike/drop detector is the honest test, and it is weak on low-count series.

### Reorder policy — SIMULATED (2026-08-02 → 2026-10-31, 91 days, 16 products, true latent demand replayed)

| Policy | Stock-out product-days | Lost units | Fill rate | Avg units on hand | Avg stock value (₹) | Orders |
|---|---|---|---|---|---|---|
| fixed | 149 | 805 | 89.4% | 357.0 | 45,465 | 148 |
| forecast_sl90 | 43 | 250 | 96.7% | 420.6 | 54,573 | 210 |
| forecast_sl95 | 32 | 241 | 96.8% | 449.2 | 59,013 | 211 |
| forecast_sl98 | 31 | 223 | 97.1% | 487.4 | 65,087 | 211 |

### Model registry & monitoring

| Version | Data as of | Holdout WAPE | Champion on same holdout | Status | Decision |
|---|---|---|---|---|---|
| v20261003-a55cdf0 | 2026-10-03 | 48.6% | — | archived | bootstrap: no production model yet |
| v20261010-cadbcdf | 2026-10-10 | 47.9% | 45.9% | rejected | candidate 0.4793 worse than champion 0.4593 beyond threshold |
| v20261017-d3e4b23 | 2026-10-17 | 49.6% | 49.6% | archived | candidate 0.4961 <= champion 0.4965 x (1+0.02) |
| v20261024-cf5c843 | 2026-10-24 | 49.1% | 49.4% | archived | candidate 0.4915 <= champion 0.4942 x (1+0.02) |
| v20261031-eed90a8 | 2026-10-31 | 49.3% | 49.1% | production | candidate 0.4927 <= champion 0.4912 x (1+0.02) |

Live accuracy of published forecasts (scored when the next week's data arrived):

| Forecast made | Scored through | Model | Live WAPE | Holdout WAPE at training |
|---|---|---|---|---|
| 2026-10-03 | 2026-10-10 | v20261003-a55cdf0 | 48.1% | 48.6% |
| 2026-10-10 | 2026-10-17 | v20261003-a55cdf0 | 53.4% | 48.6% |
| 2026-10-17 | 2026-10-24 | v20261017-d3e4b23 | 42.8% | 49.6% |
| 2026-10-24 | 2026-10-31 | v20261024-cf5c843 | 53.0% | 49.1% |

Latest drift check (2026-10-31): recent 28-day mean 73.2 units/day vs 71.4 before (shift 2.5%), KS p = 0.64907, live/holdout error ratio = 1.078 → **no alert**.
<!-- RESULTS:END -->

## What's in the repo

| Path | What it does |
|---|---|
| `app/` | The copied app (`index.html`, PWA files) plus the new `insights.js`, the published `forecasts.json` and the synthetic `data/demo_db.{json,xlsx}`. Vercel serves this folder. |
| `pipeline/generate_data.py` | Seeded synthetic shop in the app's exact `DB` schema: weekday, payday, festival, dry-day, trend and seasonal effects; stock-outs from a fixed reorder rule; planted data-quality problems with ground-truth labels. |
| `pipeline/calendar_config.py` | Festival and dry-day dates. **These are assumptions** (approximate dates, illustrative dry days). |
| `pipeline/etl.py` | Extract (JSON/xlsx) → schema validation → daily product table with stock rebuilt from the ledger → Parquet + DuckDB (category table built in SQL). |
| `forecasting/` | Seasonal naive, moving average, Holt-Winters, and a HistGradientBoosting model (Poisson loss, direct multi-horizon). Rolling-origin backtest, holdout, WAPE/MASE/bias, split-conformal 80% intervals. |
| `quality/checks.py` | Duplicate sales, credit sales with no name, sales at zero stock, ledger balance mismatches, shrinkage (shelf vs ledger), demand spikes and drops. |
| `inventory/reorder.py` | Reorder point / order-up-to policy from the forecast and its error; simulation against the fixed rule on true demand. |
| `mlops/retrain.py` | Weekly job: new data → ETL → quality → backtest → version → champion/challenger → monitoring → publish. |
| `mlops/brief.py` | Owner's weekly brief: template text, optional Gemini rephrase, automatic fallback. |
| `api/` | FastAPI service + Dockerfile. |
| `tests/` | pytest unit tests (including a no-leakage test for every model) + Playwright smoke tests of the app. |

## Design decisions

- **Static `forecasts.json` instead of a backend for the app.** The original app's hard rule is no server and zero
  running cost. The pipeline runs offline (GitHub Actions) and publishes one JSON file; the Insights tab just reads it,
  and Vercel redeploys on each commit. The FastAPI service exposes the same artifacts for integrations, but the page
  never depends on it.
- **Promote only if not worse.** Each retrain is a challenger. It replaces the production model only if its holdout
  WAPE is at most 2% (relative) worse than the champion's config **scored on the same holdout**. This stops a lucky or
  unlucky week from silently swapping models. The registry logs every decision, including rejections.
- **Event-sourced stock.** The app keeps an append-only `stockLedger`. The pipeline rebuilds stock by summing ledger
  events instead of trusting the mutable `stockQty` field. That makes stock-out days (where sales understate demand)
  identifiable, and makes ledger corruption and shrinkage detectable.
- **Honest evaluation.** Model selection uses only the rolling backtest; the holdout is scored once afterwards. Every
  model has a test proving that changing future data doesn't change its forecast. Stock-out days are excluded from
  scoring because demand is censored. Only the festival *flag* is a model feature, not the generator's true multiplier.
- **Light dependencies, LLM optional.** No torch, Prophet or TensorFlow. The core never calls a language model; the
  brief works without one.

## Running it

```bash
pip install -r requirements-dev.txt
python -m mlops.retrain --as-of 2026-10-31     # full pipeline (~2 min); omit --as-of to advance one simulated week
python -m mlops.update_readme                  # refresh the tables above
pytest -q                                      # unit + API tests
python -m playwright install chromium && RUN_E2E=1 pytest tests/e2e -q   # browser smoke tests
python -m http.server -d app 8080              # open http://localhost:8080 → Insights tab
docker build -f api/Dockerfile -t selfsense-api . && docker run -p 8000:8000 selfsense-api   # API at :8000/docs
```

Scheduled retraining (`.github/workflows/retrain.yml`) runs weekly and can be triggered manually. Each run advances
the **simulated** clock by 7 days ("new days arrive"), retrains, and commits the published results. The synthetic
world ends on 2027-06-30, so the schedule stops producing new data after about 32 runs (the job exits with a clear
message).

Optional: add a `GEMINI_API_KEY` repository secret to enable LLM rephrasing of the weekly brief. Without it, the
template brief is used.

## Limitations

- **Synthetic data only.** The models have not been validated on real shop data. The generator's structure
  (weekday/payday/festival multipliers, negative-binomial noise) is something the GBM can learn, so the real-world gain
  over the baseline could be smaller.
- Daily product-level counts are small and noisy, so product-level WAPE stays high (~0.5) even for the best model.
  Category or weekly aggregates are much more accurate.
- Sales are generated as one day-total row per product (plus occasional credit rows), not one row per customer
  transaction. This keeps the dataset small enough for browser localStorage.
- The rule-based quality checks match how the anomalies were planted, so their perfect scores are expected, not
  impressive. The statistical spike/drop detector performs poorly on low-count categories.
- The reorder simulation uses the generator's true demand and lead times. Real lead times, MOQs, case packs and cash
  constraints are not modelled. The forecast policy cuts stock-outs but holds more stock.
- Free-tier constraints: GitHub Actions minutes, Vercel hobby hosting. The API is meant to run locally or in Docker.

## Data and naming

Brand names (e.g. "Silver Crest Whisky"), supplier names and customer names are fictional placeholders. Festival
dates are approximate; dry days are an illustrative set, not an official calendar.

## License

MIT
