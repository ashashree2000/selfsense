# Forecast backtest (SYNTHETIC data, as of 2026-11-14)

Horizon 14 days. 20 rolling backtest origins (2026-01-10 .. 2026-10-03), holdout origins ['2026-10-17', '2026-10-31'].
Scoring excludes stock-out days (censored demand) and dry days. Intervals: 80% split-conformal (backtest residual quantiles 10%/90% per model x product x horizon bucket).

## Holdout (never used for selection)

| model | wape | wape_vs_naive | mase | bias | coverage_80 | n |
|---|---|---|---|---|---|---|
| gbm | 0.476 | -0.308 | 0.824 | -0.134 | 0.764 | 390 |
| holt_winters | 0.485 | -0.296 | 0.840 | -0.153 | 0.746 | 390 |
| moving_average | 0.526 | -0.236 | 0.894 | -0.116 | 0.756 | 390 |
| seasonal_naive | 0.689 | 0.000 | 1.165 | -0.069 | 0.772 | 390 |
| selected_per_category | 0.474 | -0.312 | 0.819 | -0.155 | 0.764 | 390 |

## Backtest (used for selection)

| model | wape | mase | bias | n |
|---|---|---|---|---|
| gbm | 0.504 | 0.759 | -0.043 | 4019 |
| holt_winters | 0.508 | 0.767 | -0.003 | 4019 |
| moving_average | 0.529 | 0.794 | 0.015 | 4019 |
| seasonal_naive | 0.670 | 1.008 | 0.002 | 4019 |
| selected_per_category | 0.502 | 0.758 | -0.030 | 4019 |

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
| gbm | 0.502 | -0.256 | 94 |
| holt_winters | 0.535 | -0.444 | 94 |
| moving_average | 0.521 | -0.404 | 94 |
| seasonal_naive | 0.597 | -0.479 | 94 |
| selected_per_category | 0.524 | -0.342 | 94 |

Holdout:

| model | wape | bias | n |
|---|---|---|---|
| gbm | 0.409 | -0.104 | 37 |
| holt_winters | 0.500 | -0.451 | 37 |
| moving_average | 0.515 | -0.474 | 37 |
| seasonal_naive | 0.530 | -0.455 | 37 |
| selected_per_category | 0.382 | -0.217 | 37 |

## Holdout by category

| model | category | wape | mase | bias | n |
|---|---|---|---|---|---|
| gbm | 150ml | 0.487 | 0.856 | -0.099 | 26 |
| gbm | 180ml | 0.450 | 0.812 | -0.102 | 74 |
| gbm | 375ml | 0.537 | 0.745 | -0.220 | 70 |
| gbm | 750ml | 0.639 | 0.695 | -0.080 | 52 |
| gbm | 90ml | 0.440 | 0.859 | -0.118 | 77 |
| gbm | Beer | 0.466 | 1.040 | -0.174 | 43 |
| gbm | Wine | 0.844 | 0.828 | -0.085 | 48 |
| holt_winters | 150ml | 0.451 | 0.793 | -0.200 | 26 |
| holt_winters | 180ml | 0.486 | 0.860 | -0.177 | 74 |
| holt_winters | 375ml | 0.570 | 0.795 | -0.261 | 70 |
| holt_winters | 750ml | 0.645 | 0.697 | -0.103 | 52 |
| holt_winters | 90ml | 0.433 | 0.836 | -0.181 | 77 |
| holt_winters | Beer | 0.475 | 1.075 | -0.066 | 43 |
| holt_winters | Wine | 0.867 | 0.849 | -0.140 | 48 |
| moving_average | 150ml | 0.500 | 0.880 | -0.101 | 26 |
| moving_average | 180ml | 0.514 | 0.908 | -0.151 | 74 |
| moving_average | 375ml | 0.573 | 0.797 | -0.146 | 70 |
| moving_average | 750ml | 0.657 | 0.716 | -0.034 | 52 |
| moving_average | 90ml | 0.502 | 0.967 | -0.176 | 77 |
| moving_average | Beer | 0.509 | 1.150 | -0.018 | 43 |
| moving_average | Wine | 0.891 | 0.871 | -0.141 | 48 |
| seasonal_naive | 150ml | 0.840 | 1.478 | 0.188 | 26 |
| seasonal_naive | 180ml | 0.668 | 1.179 | -0.147 | 74 |
| seasonal_naive | 375ml | 0.745 | 1.037 | -0.169 | 70 |
| seasonal_naive | 750ml | 0.774 | 0.826 | -0.065 | 52 |
| seasonal_naive | 90ml | 0.639 | 1.236 | -0.147 | 77 |
| seasonal_naive | Beer | 0.661 | 1.446 | 0.054 | 43 |
| seasonal_naive | Wine | 1.170 | 1.158 | -0.021 | 48 |
| selected_per_category | 150ml | 0.487 | 0.856 | -0.099 | 26 |
| selected_per_category | 180ml | 0.450 | 0.812 | -0.102 | 74 |
| selected_per_category | 375ml | 0.537 | 0.745 | -0.220 | 70 |
| selected_per_category | 750ml | 0.639 | 0.695 | -0.080 | 52 |
| selected_per_category | 90ml | 0.433 | 0.836 | -0.181 | 77 |
| selected_per_category | Beer | 0.466 | 1.040 | -0.174 | 43 |
| selected_per_category | Wine | 0.844 | 0.828 | -0.085 | 48 |
