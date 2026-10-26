# Workload Model — from users to tokens per second

All figures in examples are illustrative placeholders to show the arithmetic; replace with measured values.

## Inputs
| Symbol | Input | Typical source |
|---|---|---|
| U | Daily active users | product / HR headcount |
| r | Requests per user per day | logs or pilot; else assumption |
| T_in | Average input tokens per request (prompt + context + history) | logs; RAG adds context tokens |
| T_out | Average output tokens per request | logs |
| H | Active hours per day over which load is spread | business hours (e.g., 10) or 24 |
| p | Peak factor: peak requests/s ÷ average requests/s during active hours | logs; 2–4 common for business apps (assumption) |
| C | Context length cap | model/config |
| SLO | TTFT target (s) and decode tokens/s per stream, or e2e p95 | product |

## Derivations
```
Requests/day            R_day   = U × r
Average requests/s      R_avg   = R_day / (H × 3600)
Peak requests/s         R_peak  = R_avg × p
Prefill tokens/s (peak) P_peak  = R_peak × T_in
Decode tokens/s (peak)  D_peak  = R_peak × T_out
Concurrent streams      N_conc  = R_peak × (T_out / s_user)      where s_user = tokens/s delivered per stream (SLO)
                        (Little's law: concurrency = arrival rate × time in system)
```

## Illustrative walk-through (placeholder numbers, not a benchmark)
| Step | Value |
|---|---|
| U = 1,000 users; r = 20 req/day | R_day = 20,000 |
| H = 10 h | R_avg = 0.56 req/s |
| p = 3 | R_peak = 1.67 req/s |
| T_in = 1,500; T_out = 300 | P_peak ≈ 2,500 tok/s; D_peak ≈ 500 tok/s |
| s_user = 20 tok/s | N_conc ≈ 1.67 × 15 s ≈ 25 streams |

## Scenario table (fill)
| Scenario | U | r | T_in | T_out | p | R_peak | P_peak | D_peak | N_conc |
|---|---|---|---|---|---|---|---|---|---|
| Low | | | | | | | | | |
| Expected | | | | | | | | | |
| Peak / growth | | | | | | | | | |

## Rules
1. Separate prefill (input) from decode (output); they stress the GPU differently (compute-bound vs memory-bandwidth-bound).
2. Use peak, not average, for capacity; use average for cost of API options.
3. Include agentic multipliers: an agent run may make 5–20 model calls per user request (assumption); model it as r × calls per request.
4. Batch workloads (nightly summarization) are sized separately and can use off-peak capacity.
