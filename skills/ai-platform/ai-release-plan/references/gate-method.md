# Gate evaluation and duration method

## Gates
Each gate row is `stage, metric, min, max`. A gate is **met** when the fact named by `metric` is
numeric and `min <= actual <= max` (an empty bound is not checked). Status values:

| Status | Meaning |
|---|---|
| met | fact present and within bounds |
| NOT MET | fact present and outside bounds |
| not measured | no numeric fact for the metric yet — never treated as met |

Gates are evaluated **now**, from the facts supplied. Only the first stage (`offline_eval`) blocks
the run: if any `offline_eval` gate is not met, or no `offline_eval` gate exists, the script still
writes the plan and exits 1. Later-stage gates are re-evaluated with live metrics during rollout.

## Minimum stage duration
```
hours = ceil( min_observed_requests / (daily_requests × traffic_pct / 100 / 24) )
```
Shadow uses 100 % (mirrored traffic). Offline eval and GA have no duration (sign-off gates).
Missing `daily_requests` or `min_observed_requests` → duration `[TO BE BASELINED — owner: Release manager]`.
The request count is an owner input chosen for statistical confidence; the skill does not pick it.

Worked example (fictional fixture): 2,000 requests at 48,000/day on a 5 % canary →
48,000 × 0.05 / 24 = 100 requests/hour → 20 hours.

## Rollback triggers
Every gate on `shadow`, `canary` or `ga` becomes a trigger: `metric > max` or `metric < min` while
that stage is live → stop the stage (shadow) or roll back (served stages). `rollback_time_min` is
reported as stated; if absent it is TBD with the Release manager.
