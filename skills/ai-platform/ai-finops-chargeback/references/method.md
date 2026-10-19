# Method — AI showback / chargeback

## Inputs
| File | Columns | Notes |
|---|---|---|
| usage | date, team, feature, model, requests, input_tokens, output_tokens[, cached_input_tokens] | one row per day × team × feature × model (finer rows are summed); `input_tokens` includes cached tokens |
| prices | model, input_per_1m, output_per_1m[, cached_input_per_1m], effective_from[, source] | several rows per model allowed; the latest `effective_from` on or before the usage date applies |
| budgets | team, month (YYYY-MM), budget_usd | optional; a team-month with usage and no row reads `[TO BE BASELINED — owner: FinOps lead]` |

## Formulas
| Quantity | Formula |
|---|---|
| Row cost | ((input − cached) × input_per_1m + cached × cached rate + output × output_per_1m) ÷ 1M; cached rate = `cached_input_per_1m`, else the full input price (noted in the report) |
| Unpriced row | model absent from the sheet, or no row in effect on the date → no cost, `[TO BE BASELINED — owner: FinOps lead]`, excluded from every total, anomaly and forecast |
| Cost per 1k requests | spend ÷ priced requests × 1k, 4 decimals |
| Share | detail and month_team rows: % of that month's priced spend; other rows: % of all priced spend; 2 decimals |
| Month-over-month | (month − prior calendar month) ÷ prior month × 100; `n/a` without a prior month |
| Anomaly | team-day spend > mean + 3 × sample sd of the team's previous 14 calendar days (no-usage days = 0; days before the team's first usage excluded); evaluated only with ≥ 7 prior days |
| Forecast | closed month = actual; as-of month = actual ÷ days elapsed × days in month; later month = not started |
| Variance | budget − forecast (negative = over budget); status OVER BUDGET when forecast > budget |

Precision: `decimal.Decimal` throughout; money rounded half-up to cents only when written; rollup rows are rounded from their full-precision sums. `--as-of` defaults to the latest usage date (never today).

## showback.csv levels
`total`, `month`, `month_team`, `team`, `team_feature`, `model`, `detail` (month × team × feature × model). Unused dimensions read `*`. Sum only one level at a time.

## Worked example (the eval fixture — fictional prices, hand-checked)
Prices per 1M tokens: fict-large 3.00 in / 15.00 out / 0.30 cached from 2026-08-01, then 2.50 / 15.00 / 0.25 from 2026-09-15; fict-small 0.25 / 1.25, no cached price.

| Line | Daily usage | Daily cost |
|---|---|---|
| billing-support · invoice-qa · fict-large | 1,000 req; 2.0M in (0.5M cached); 0.3M out | to 09-14: 1.5 × 3 + 0.5 × 0.30 + 0.3 × 15 = 9.15; from 09-15: 3.75 + 0.125 + 4.50 = 8.375 |
| billing-support · dispute-summary · fict-small | 333 req; 777,777 in (100,000 cached, full price); 111,111 out | 0.19444425 + 0.13888875 = 0.333333 |
| collections · dunning-email · fict-small | 500 req (odd days) / 520 (even); 800 in and 200 out per request; 5,000 req on 09-25 | 450 × req ÷ 1M: 0.225 / 0.234; 2.25 on 09-25 |
| billing-support · invoice-qa · fict-legacy | 200 req on 10-01..10-03 | unpriced (no price row) |

- September: invoice-qa 14 × 9.15 + 16 × 8.375 = 262.10; dispute-summary 30 × 0.333333 = 9.99999 → 10.00; billing-support 272.09999 → **272.10**; collections 15 × 0.225 + 15 × 0.234 + 2.025 = **8.91**; month **281.01**.
- October 1–10: billing-support 83.75 + 3.33333 = 87.08333 → 87.08, forecast 87.08333 ÷ 10 × 31 = **269.96** vs budget 250.00 → variance **−19.96, OVER BUDGET**; collections 2.295 → 2.30, forecast **7.11**, variance 2.89.
- Total **370.39** = 281.01 + 89.38 = 359.18 + 11.21 (reconciles to the cent).
- Anomaly 2026-09-25 collections: trailing 14 days mean 0.2295, sample sd 0.0047, threshold 0.2435; spend 2.25, excess 2.01.

## Using the output
- Showback: publish `showback.csv` (team and team_feature levels) to each team monthly.
- Chargeback: Finance posts the `month_team` amounts only once unpriced usage is priced and the figures are reconciled to the provider invoice; this skill does not reconcile invoices.
- Anomalies go to the team's engineering lead to confirm cause before any adjustment.
