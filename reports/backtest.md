# Forecast backtest (SYNTHETIC data, as of 2026-11-07)

Horizon 14 days. 20 rolling backtest origins (2026-01-03 .. 2026-09-26), holdout origins ['2026-10-10', '2026-10-24'].
Scoring excludes stock-out days (censored demand) and dry days. Intervals: 80% split-conformal (backtest residual quantiles 10%/90% per model x product x horizon bucket).

## Holdout (never used for selection)

| model | wape | wape_vs_naive | mase | bias | coverage_80 | n |
|---|---|---|---|---|---|---|
| gbm | 0.514 | -0.218 | 0.849 | -0.170 | 0.756 | 389 |
| holt_winters | 0.498 | -0.242 | 0.843 | -0.154 | 0.774 | 389 |
| moving_average | 0.549 | -0.165 | 0.916 | -0.137 | 0.738 | 389 |
| seasonal_naive | 0.657 | 0.000 | 1.126 | -0.090 | 0.794 | 389 |
| selected_per_category | 0.514 | -0.218 | 0.849 | -0.170 | 0.756 | 389 |

## Backtest (used for selection)

| model | wape | mase | bias | n |
|---|---|---|---|---|
| gbm | 0.497 | 0.753 | -0.030 | 4020 |
| holt_winters | 0.509 | 0.770 | 0.009 | 4020 |
| moving_average | 0.523 | 0.788 | 0.018 | 4020 |
| seasonal_naive | 0.699 | 1.044 | 0.020 | 4020 |
| selected_per_category | 0.497 | 0.753 | -0.030 | 4020 |

## Model selected per category (lowest backtest WAPE)

- 150ml: gbm
- 180ml: gbm
- 375ml: gbm
- 750ml: gbm
- 90ml: gbm
- Beer: gbm
- Wine: gbm

## Festival days

Backtest windows:

| model | wape | bias | n |
|---|---|---|---|
| gbm | 0.434 | -0.193 | 81 |
| holt_winters | 0.521 | -0.400 | 81 |
| moving_average | 0.489 | -0.337 | 81 |
| seasonal_naive | 0.676 | -0.284 | 81 |
| selected_per_category | 0.434 | -0.193 | 81 |

Holdout:

| model | wape | bias | n |
|---|---|---|---|
| gbm | 0.497 | -0.451 | 36 |
| holt_winters | 0.527 | -0.510 | 36 |
| moving_average | 0.572 | -0.572 | 36 |
| seasonal_naive | 0.628 | -0.604 | 36 |
| selected_per_category | 0.497 | -0.451 | 36 |

## Holdout by category

| model | category | wape | mase | bias | n |
|---|---|---|---|---|---|
| gbm | 150ml | 0.525 | 1.059 | -0.283 | 24 |
| gbm | 180ml | 0.428 | 0.748 | -0.117 | 75 |
| gbm | 375ml | 0.586 | 0.718 | -0.149 | 73 |
| gbm | 750ml | 0.616 | 0.569 | 0.022 | 50 |
| gbm | 90ml | 0.499 | 0.938 | -0.126 | 77 |
| gbm | Beer | 0.532 | 1.306 | -0.261 | 42 |
| gbm | Wine | 0.864 | 0.852 | -0.124 | 48 |
| holt_winters | 150ml | 0.483 | 0.975 | -0.299 | 24 |
| holt_winters | 180ml | 0.460 | 0.783 | -0.144 | 75 |
| holt_winters | 375ml | 0.605 | 0.741 | -0.168 | 73 |
| holt_winters | 750ml | 0.669 | 0.624 | 0.100 | 50 |
| holt_winters | 90ml | 0.507 | 0.953 | -0.156 | 77 |
| holt_winters | Beer | 0.444 | 1.096 | -0.151 | 42 |
| holt_winters | Wine | 0.864 | 0.851 | -0.152 | 48 |
| moving_average | 150ml | 0.537 | 1.085 | -0.363 | 24 |
| moving_average | 180ml | 0.493 | 0.835 | -0.089 | 75 |
| moving_average | 375ml | 0.665 | 0.820 | -0.032 | 73 |
| moving_average | 750ml | 0.690 | 0.652 | 0.184 | 50 |
| moving_average | 90ml | 0.559 | 1.050 | -0.149 | 77 |
| moving_average | Beer | 0.508 | 1.254 | -0.171 | 42 |
| moving_average | Wine | 0.885 | 0.871 | -0.115 | 48 |
| seasonal_naive | 150ml | 0.493 | 0.996 | -0.322 | 24 |
| seasonal_naive | 180ml | 0.594 | 1.040 | -0.125 | 75 |
| seasonal_naive | 375ml | 0.820 | 1.015 | 0.138 | 73 |
| seasonal_naive | 750ml | 0.973 | 0.907 | 0.013 | 50 |
| seasonal_naive | 90ml | 0.673 | 1.276 | -0.099 | 77 |
| seasonal_naive | Beer | 0.608 | 1.525 | -0.084 | 42 |
| seasonal_naive | Wine | 1.149 | 1.133 | 0.085 | 48 |
| selected_per_category | 150ml | 0.525 | 1.059 | -0.283 | 24 |
| selected_per_category | 180ml | 0.428 | 0.748 | -0.117 | 75 |
| selected_per_category | 375ml | 0.586 | 0.718 | -0.149 | 73 |
| selected_per_category | 750ml | 0.616 | 0.569 | 0.022 | 50 |
| selected_per_category | 90ml | 0.499 | 0.938 | -0.126 | 77 |
| selected_per_category | Beer | 0.532 | 1.306 | -0.261 | 42 |
| selected_per_category | Wine | 0.864 | 0.852 | -0.124 | 48 |
