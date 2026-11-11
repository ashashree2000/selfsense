# Data-quality checks (SYNTHETIC data, as of 2026-11-07)

Scored against the anomalies planted by the generator.

| check | planted | flagged | TP | precision | recall |
|---|---|---|---|---|---|
| duplicate_sale | 7 | 7 | 7 | 1.00 | 1.00 |
| credit_sale_no_name | 10 | 10 | 10 | 1.00 | 1.00 |
| sale_at_zero_stock | 14 | 14 | 14 | 1.00 | 1.00 |
| ledger_balance_mismatch | 11 | 11 | 11 | 1.00 | 1.00 |
| shrinkage | 3 | 3 | 3 | 1.00 | 1.00 |
| demand_spike | 9 | 14 | 4 | 0.29 | 0.44 |
| demand_drop | 6 | 6 | 1 | 0.17 | 0.17 |
