# Sources (checked 2026-10-18)

| Item | Source | What it supports |
|---|---|---|
| Burn rate definition | Google SRE workbook, ch. 5 "Alerting on SLOs" — https://sre.google/workbook/alerting-on-slos/ | "Burn rate is how fast, relative to the SLO, the service consumes the error budget." A burn rate of 1 spends exactly the budget over the SLO window. |
| Multiwindow, multi-burn-rate thresholds | same page, Table 5-8 "Recommended parameters for a 99.9% SLO alerting configuration" | Page: 1 h long / 5 m short window, burn rate 14.4, 2% of budget consumed. Page: 6 h / 30 m, burn rate 6, 5%. Ticket: 3 d / 6 h, burn rate 1, 10%. |
| Short window length | same page | Guideline: the short window is 1/12 of the long window. |
| Threshold formula | same page (worked examples use a 30-day SLO period) | Budget consumed by the time an alert fires = burn rate × alert window ÷ SLO period; so 14.4 × 1 h ÷ 720 h = 2%. The script inverts this: threshold = budget share × window hours ÷ long-window hours, which reproduces 14.4 / 6 / 1 for 30 days and scales them for other `window_days`. |

Short paraphrases only; read the workbook for the full reasoning (precision, recall, detection and reset time).

Nearest-rank percentile and the error-budget arithmetic (budget = 1 − objective; consumed = (1 − SLI)/(1 − objective)) are standard definitions and need no external source. The proposal ladders (`0.9 … 0.9999`, `0.8 … 0.99`) and "p95 rounded up" rule are this skill's own convention for drafting objectives; they are labelled proposals and owned by the Product owner.
