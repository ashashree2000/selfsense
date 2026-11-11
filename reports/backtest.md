# Forecast backtest (SYNTHETIC data, as of 2026-10-31)

Horizon 14 days. 20 rolling backtest origins (2025-12-27 .. 2026-09-19), holdout origins ['2026-10-03', '2026-10-17'].
Scoring excludes stock-out days (censored demand) and dry days. Intervals: 80% split-conformal (backtest residual quantiles 10%/90% per model x product x horizon bucket).

## Holdout (never used for selection)

| model | wape | wape_vs_naive | mase | bias | coverage_80 | n |
|---|---|---|---|---|---|---|
| gbm | 0.492 | -0.269 | 0.796 | -0.161 | 0.812 | 398 |
| holt_winters | 0.497 | -0.262 | 0.809 | -0.105 | 0.806 | 398 |
| moving_average | 0.536 | -0.204 | 0.873 | -0.122 | 0.766 | 398 |
| seasonal_naive | 0.674 | 0.000 | 1.079 | -0.049 | 0.814 | 398 |
| selected_per_category | 0.493 | -0.269 | 0.797 | -0.148 | 0.809 | 398 |

## Backtest (used for selection)

| model | wape | mase | bias | n |
|---|---|---|---|---|
| gbm | 0.502 | 0.765 | -0.046 | 4011 |
| holt_winters | 0.505 | 0.772 | -0.012 | 4011 |
| moving_average | 0.525 | 0.796 | 0.012 | 4011 |
| seasonal_naive | 0.668 | 1.020 | -0.001 | 4011 |
| selected_per_category | 0.500 | 0.763 | -0.034 | 4011 |

## Model selected per category (lowest backtest WAPE)

- 150ml: gbm
- 180ml: gbm
- 375ml: gbm
- 750ml: gbm
- 90ml: holt_winters
- Beer: gbm
- Wine: gbm

## Festival days

Backtest windows:

| model | wape | bias | n |
|---|---|---|---|
| gbm | 0.499 | -0.251 | 96 |
| holt_winters | 0.576 | -0.476 | 96 |
| moving_average | 0.519 | -0.385 | 96 |
| seasonal_naive | 0.598 | -0.456 | 96 |
| selected_per_category | 0.536 | -0.347 | 96 |

Holdout:

| model | wape | bias | n |
|---|---|---|---|
| gbm | 0.446 | -0.331 | 36 |
| holt_winters | 0.520 | -0.502 | 36 |
| moving_average | 0.556 | -0.553 | 36 |
| seasonal_naive | 0.562 | -0.524 | 36 |
| selected_per_category | 0.444 | -0.376 | 36 |

## Holdout by category

| model | category | wape | mase | bias | n |
|---|---|---|---|---|---|
| gbm | 150ml | 0.487 | 0.859 | -0.202 | 26 |
| gbm | 180ml | 0.449 | 0.697 | -0.067 | 78 |
| gbm | 375ml | 0.548 | 0.720 | -0.195 | 75 |
| gbm | 750ml | 0.589 | 0.638 | -0.094 | 48 |
| gbm | 90ml | 0.506 | 0.856 | -0.101 | 79 |
| gbm | Beer | 0.447 | 1.048 | -0.278 | 43 |
| gbm | Wine | 0.913 | 0.872 | -0.110 | 49 |
| holt_winters | 150ml | 0.463 | 0.817 | -0.252 | 26 |
| holt_winters | 180ml | 0.464 | 0.707 | -0.096 | 78 |
| holt_winters | 375ml | 0.587 | 0.773 | -0.215 | 75 |
| holt_winters | 750ml | 0.619 | 0.674 | -0.058 | 48 |
| holt_winters | 90ml | 0.507 | 0.861 | -0.060 | 79 |
| holt_winters | Beer | 0.444 | 1.040 | -0.100 | 43 |
| holt_winters | Wine | 0.910 | 0.870 | -0.119 | 49 |
| moving_average | 150ml | 0.502 | 0.886 | -0.285 | 26 |
| moving_average | 180ml | 0.497 | 0.755 | -0.023 | 78 |
| moving_average | 375ml | 0.618 | 0.819 | -0.180 | 75 |
| moving_average | 750ml | 0.672 | 0.740 | -0.012 | 48 |
| moving_average | 90ml | 0.550 | 0.923 | -0.056 | 79 |
| moving_average | Beer | 0.478 | 1.127 | -0.218 | 43 |
| moving_average | Wine | 1.017 | 0.962 | -0.090 | 49 |
| seasonal_naive | 150ml | 0.729 | 1.285 | -0.132 | 26 |
| seasonal_naive | 180ml | 0.709 | 1.046 | 0.098 | 78 |
| seasonal_naive | 375ml | 0.798 | 1.039 | -0.153 | 75 |
| seasonal_naive | 750ml | 0.821 | 0.882 | -0.059 | 48 |
| seasonal_naive | 90ml | 0.653 | 1.101 | -0.051 | 79 |
| seasonal_naive | Beer | 0.575 | 1.308 | -0.084 | 43 |
| seasonal_naive | Wine | 1.087 | 1.036 | -0.130 | 49 |
| selected_per_category | 150ml | 0.487 | 0.859 | -0.202 | 26 |
| selected_per_category | 180ml | 0.449 | 0.697 | -0.067 | 78 |
| selected_per_category | 375ml | 0.548 | 0.720 | -0.195 | 75 |
| selected_per_category | 750ml | 0.589 | 0.638 | -0.094 | 48 |
| selected_per_category | 90ml | 0.507 | 0.861 | -0.060 | 79 |
| selected_per_category | Beer | 0.447 | 1.048 | -0.278 | 43 |
| selected_per_category | Wine | 0.913 | 0.872 | -0.110 | 49 |
