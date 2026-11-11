# Reorder policy simulation (SIMULATED on SYNTHETIC data)

Window 2026-08-16 .. 2026-11-14 (91 days, 16 products). True latent demand replayed; forecasts refreshed every 7 days using only past data.

| policy | stockout_product_days | stockout_rate | lost_units | fill_rate | avg_units_on_hand | avg_stock_value | orders_placed |
|---|---|---|---|---|---|---|---|
| fixed | 134 | 0.092 | 937.0 | 0.8806 | 354.8 | 46164.0 | 148 |
| forecast_sl90 | 38 | 0.0261 | 253.0 | 0.9678 | 422.8 | 55586.0 | 207 |
| forecast_sl95 | 23 | 0.0158 | 171.0 | 0.9782 | 454.7 | 60283.0 | 212 |
| forecast_sl98 | 22 | 0.0151 | 161.0 | 0.9795 | 493.8 | 65808.0 | 212 |
