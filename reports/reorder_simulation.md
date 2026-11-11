# Reorder policy simulation (SIMULATED on SYNTHETIC data)

Window 2026-08-02 .. 2026-10-31 (91 days, 16 products). True latent demand replayed; forecasts refreshed every 7 days using only past data.

| policy | stockout_product_days | stockout_rate | lost_units | fill_rate | avg_units_on_hand | avg_stock_value | orders_placed |
|---|---|---|---|---|---|---|---|
| fixed | 149 | 0.1023 | 805.0 | 0.8937 | 357.0 | 45465.0 | 148 |
| forecast_sl90 | 43 | 0.0295 | 250.0 | 0.967 | 420.6 | 54573.0 | 210 |
| forecast_sl95 | 32 | 0.022 | 241.0 | 0.9682 | 449.2 | 59013.0 | 211 |
| forecast_sl98 | 31 | 0.0213 | 223.0 | 0.9706 | 487.4 | 65087.0 | 211 |
