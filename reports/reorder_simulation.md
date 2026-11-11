# Reorder policy simulation (SIMULATED on SYNTHETIC data)

Window 2026-08-09 .. 2026-11-07 (91 days, 16 products). True latent demand replayed; forecasts refreshed every 7 days using only past data.

| policy | stockout_product_days | stockout_rate | lost_units | fill_rate | avg_units_on_hand | avg_stock_value | orders_placed |
|---|---|---|---|---|---|---|---|
| fixed | 133 | 0.0913 | 658.0 | 0.914 | 355.5 | 46161.0 | 149 |
| forecast_sl90 | 33 | 0.0227 | 137.0 | 0.9821 | 414.6 | 54546.0 | 209 |
| forecast_sl95 | 21 | 0.0144 | 91.0 | 0.9881 | 445.6 | 59218.0 | 211 |
| forecast_sl98 | 22 | 0.0151 | 79.0 | 0.9897 | 482.7 | 64688.0 | 212 |
