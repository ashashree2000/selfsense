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
_Auto-generated from `reports/*.json` by `mlops/update_readme.py`. Data as of **2026-11-07**. All data is SYNTHETIC._

### Forecast accuracy — holdout (last 28 days, never used for model selection)

Product-level daily forecasts, 14-day horizon. Stock-out and dry days excluded from scoring.

| Model | WAPE | vs seasonal naive | MASE | Bias | 80% interval coverage |
|---|---|---|---|---|---|
| seasonal_naive | 65.7% | +0.0% | 1.126 | -9.0% | 79.4% |
| moving_average | 54.9% | -16.5% | 0.916 | -13.7% | 73.8% |
| holt_winters | 49.8% | -24.2% | 0.843 | -15.4% | 77.4% |
| gbm | 51.4% | -21.8% | 0.849 | -17.0% | 75.6% |
| selected_per_category | 51.4% | -21.8% | 0.849 | -17.0% | 75.6% |

Rolling-origin backtest (20 origins, 2026-01-03 → 2026-09-26): seasonal_naive WAPE 69.9%, moving_average WAPE 52.3%, holt_winters WAPE 50.9%, gbm WAPE 49.8%, selected_per_category WAPE 49.8%.

Model selected per category (by backtest WAPE): 150ml → gbm, 180ml → gbm, 375ml → gbm, 750ml → gbm, 90ml → gbm, Beer → gbm, Wine → gbm.

**Festival days** (WAPE / bias):

| Model | Backtest windows | Holdout |
|---|---|---|
| seasonal_naive | 67.6% / -28.4% (n=81) | 62.8% / -60.4% (n=36) |
| moving_average | 48.9% / -33.7% (n=81) | 57.2% / -57.2% (n=36) |
| holt_winters | 52.1% / -40.0% (n=81) | 52.7% / -51.0% (n=36) |
| gbm | 43.4% / -19.3% (n=81) | 49.7% / -45.1% (n=36) |
| selected_per_category | 43.4% / -19.3% (n=81) | 49.7% / -45.1% (n=36) |

### Data-quality checks vs planted anomalies

| Check | Planted | Flagged | Precision | Recall |
|---|---|---|---|---|
| duplicate_sale | 7 | 7 | 100.0% | 100.0% |
| credit_sale_no_name | 10 | 10 | 100.0% | 100.0% |
| sale_at_zero_stock | 14 | 14 | 100.0% | 100.0% |
| ledger_balance_mismatch | 11 | 11 | 100.0% | 100.0% |
| shrinkage | 3 | 3 | 100.0% | 100.0% |
| demand_spike | 9 | 14 | 28.6% | 44.4% |
| demand_drop | 6 | 6 | 16.7% | 16.7% |

The five rule-based checks are exact by construction on this synthetic data (each rule mirrors how the anomaly was planted). The statistical spike/drop detector is the honest test, and it is weak on low-count series.

### Reorder policy — SIMULATED (2026-08-09 → 2026-11-07, 91 days, 16 products, true latent demand replayed)

| Policy | Stock-out product-days | Lost units | Fill rate | Avg units on hand | Avg stock value (₹) | Orders |
|---|---|---|---|---|---|---|
| fixed | 133 | 658 | 91.4% | 355.5 | 46,161 | 149 |
| forecast_sl90 | 33 | 137 | 98.2% | 414.6 | 54,546 | 209 |
| forecast_sl95 | 21 | 91 | 98.8% | 445.6 | 59,218 | 211 |
| forecast_sl98 | 22 | 79 | 99.0% | 482.7 | 64,688 | 212 |

### Model registry & monitoring

| Version | Data as of | Holdout WAPE | Champion on same holdout | Status | Decision |
|---|---|---|---|---|---|
| v20261003-a55cdf0 | 2026-10-03 | 48.6% | — | archived | bootstrap: no production model yet |
| v20261010-cadbcdf | 2026-10-10 | 47.9% | 45.9% | rejected | candidate 0.4793 worse than champion 0.4593 beyond threshold |
| v20261017-d3e4b23 | 2026-10-17 | 49.6% | 49.6% | archived | candidate 0.4961 <= champion 0.4965 x (1+0.02) |
| v20261024-cf5c843 | 2026-10-24 | 49.1% | 49.4% | archived | candidate 0.4915 <= champion 0.4942 x (1+0.02) |
| v20261031-eed90a8 | 2026-10-31 | 49.3% | 49.1% | archived | candidate 0.4927 <= champion 0.4912 x (1+0.02) |
| v20261107-f26f9a6 | 2026-11-07 | 51.4% | 51.6% | production | candidate 0.5138 <= champion 0.5165 x (1+0.02) |

Live accuracy of published forecasts (scored when the next week's data arrived):

| Forecast made | Scored through | Model | Live WAPE | Holdout WAPE at training |
|---|---|---|---|---|
| 2026-10-03 | 2026-10-10 | v20261003-a55cdf0 | 48.1% | 48.6% |
| 2026-10-10 | 2026-10-17 | v20261003-a55cdf0 | 53.4% | 48.6% |
| 2026-10-17 | 2026-10-24 | v20261017-d3e4b23 | 42.8% | 49.6% |
| 2026-10-24 | 2026-10-31 | v20261024-cf5c843 | 53.0% | 49.1% |
| 2026-10-31 | 2026-11-07 | v20261031-eed90a8 | 50.5% | 49.3% |

Latest drift check (2026-11-07): recent 28-day mean 78.0 units/day vs 71.4 before (shift 9.2%), KS p = 0.28055, live/holdout error ratio = 1.025 → **no alert**.
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
