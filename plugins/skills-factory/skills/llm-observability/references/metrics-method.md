# Metrics method

All numbers are computed from the spans supplied; nothing is estimated or defaulted.

## Windows
| Window | Spans |
|---|---|
| Baseline (optional) | `baseline-start <= ts <= baseline-end`; a bare date is the whole UTC day |
| Current | spans after `baseline-end`; all spans when no baseline is given |
| Excluded | spans before `baseline-start` (counted, not used) |
| SLO window | `all`, or `<n>m` / `<n>h` / `<n>d` back from the newest current-window span |

## Metrics (per feature and overall, current window)
| Metric | Definition |
|---|---|
| requests | span count |
| error_rate | spans with `status = error` ÷ requests |
| latency_p50/p95/p99_ms | nearest-rank percentile over all spans (ok and error) |
| tokens_per_request | mean of `input_tokens + output_tokens` |
| cost_per_request_usd | mean `cost_usd` over spans that carry it; `cost_coverage` = share of spans with cost. Never estimated from token prices |
| eval_score_mean | mean `eval_score` over spans that carry it (`eval_coverage` reported) |
| negative_feedback_rate | `down ÷ (up + down)` over spans with feedback |

### Percentile (exact method)
Nearest-rank: sort the n latencies ascending; the p-th percentile is the value at 1-based rank
`ceil(p/100 × n)`. It always returns an observed value (no interpolation). Example: 20 spans,
p95 → rank 19.

## Drift
`drift_<metric>_pct = (current − baseline) ÷ baseline × 100` for tokens_per_request,
latency_p95_ms and eval_score_mean, overall and per feature (only where both windows have spans).
Drift is reported, and alerts only where an SLO row names a `drift_*_pct` metric (compared on the
absolute value).

## SLO evaluation
SLO rows: `metric, threshold, window[, feature][, comparator]`. Default comparator: `>=` for
`eval_score_mean`, `<=` for every other metric. Status: OK, BREACH, or NO DATA (metric absent in
the window — reported, never counted as met). Any BREACH → exit 1.

## Related public practice (by name)
- Google SRE Book, "Service Level Objectives" — SLIs, SLOs and windows.
- OpenTelemetry semantic conventions for generative AI — span attribute naming for model calls.
- NIST AI RMF 1.0, *Measure* and *Manage* functions — ongoing monitoring of deployed AI.
