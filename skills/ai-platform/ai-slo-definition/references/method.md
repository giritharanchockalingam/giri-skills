# SLO method (what `scripts/slo.py` computes)

## Log
`timestamp, latency_ms, status[, quality_pass][, cost_usd]`. Rows are sorted by timestamp. Timestamps must all carry a UTC offset or all omit it. `status` is `ok` or `error`; `quality_pass` is `0`, `1` or blank; `cost_usd` is a number or blank.

## SLIs (good events ÷ eligible events)
| SLI | Eligible | Good |
|---|---|---|
| availability | every request | `status = ok` |
| latency | ok requests with a latency | `latency_ms <= threshold` |
| quality | rows with `quality_pass` | `quality_pass = 1` |
| cost | rows with `cost_usd` | `cost_usd <= threshold` |

Latency counts ok requests only: failed requests already count against availability, and fast failures would flatter latency.

## Error budget, consumption, burn rate
- Error budget `= 1 − objective`.
- Budget consumed `= (1 − SLI) / (1 − objective)` over the whole log — equal to the burn rate over the log span. It is the share of the window's budget used if the log is representative of the SLO window. `> 1` is **breached** (gate, exit 1).
- Budget spent to date `= consumed × log span ÷ SLO window` (shown when `window_days` is given).
- Window burn rate `= (bad ÷ eligible in the window) / (1 − objective)`, windows `(T − w, T]` ending at the last log timestamp `T`. A window the log does not cover (first timestamp later than `T − w`) or with no eligible events is `n/a`.
- `burn_rate` in `slos.csv` is the last-1 h window; every window is in `slo.json` and the Alerting policy section.
- All ratios are exact fractions (no float rounding at the `> 1` boundary); outputs round half-up (observed 5 dp, consumed and burn 3 dp).

## Alerting policy (SRE workbook table 5-8, see `references/sources.md`)
| Alert | Long / short window | Budget share | Threshold at 30 days |
|---|---|---|---|
| fast-burn page | 1 h / 5 m | 2% | 14.4 |
| slow-burn page | 6 h / 30 m | 5% | 6 |
| ticket | 3 d / 6 h | 10% | 1 |

Threshold = share × window_days × 24 ÷ long-window hours. An alert fires when both the long and the short window burn at or above it. Any firing alert on an agreed SLO that is not breached makes it **at-risk**. Without `window_days` the 30-day reference is used and the window is marked `[TO BE BASELINED — owner: SRE lead]`.

## Proposals (no target for an SLI)
- availability / quality: highest level on the ladder not above the observed SLI (availability `0.9, 0.95, 0.99, 0.995, 0.999, 0.9995, 0.9999`; quality `0.8, 0.85, 0.9, 0.95, 0.98, 0.99`). None fits → objective `[TO BE BASELINED — owner: Product owner]`.
- latency: threshold = observed nearest-rank p95 of ok requests rounded up to the next 100 ms; objective 0.95.
- cost: threshold = observed p95 cost rounded up to the next 0.001 USD; objective 0.95.
- Status `proposed`, note `[TO BE BASELINED — owner: Product owner]`. Proposals are never gated: they describe current behaviour, not an agreed commitment.

## Percentiles
Nearest-rank: sort ascending, take the value at rank `ceil(p/100 × n)` (1-based). No interpolation, so the result is always an observed value.

## Worked example (eval fixture, hand-checked)
480 requests one minute apart (00:00–07:59). Errors at i = 7, 207, 407; `quality_pass = 0` when i mod 25 = 3 (20 rows); latency = 800 + (37·i mod 900); cost = 0.0020 + 0.0001·(i mod 10).
- availability: 477/480 = **0.99375**; objective 0.99 → consumed 0.00625/0.01 = **0.625**; last hour (i ≥ 420) has no error → burn **0.000** → met.
- latency ≤ 1650 ms: 451 of 477 ok requests = **0.94549**; objective 0.9 → consumed (26/477)/0.1 = **0.545**.
- quality: 460/480 = **0.95833**; objective 0.95 → consumed **0.833**; last hour has 3 fails in 60 (i = 428, 453, 478) → burn 0.05/0.05 = **1.000**.
- cost ≤ 0.0028: 432/480 = **0.90000**; objective 0.8 → consumed **0.500**.
- Latency nearest-rank on 477 ok values: p50 rank 239 = **1238 ms**, p95 rank 454 = **1653 ms** → proposed threshold **1700 ms**.
