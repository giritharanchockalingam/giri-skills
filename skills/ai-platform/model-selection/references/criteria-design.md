# Criteria Design — what to score, what to constrain

## Typical criteria (choose; do not use all)
| Criterion | Direction | Usually | Evidence the user supplies |
|---|---|---|---|
| Task eval score (own golden set) | higher | weighted, often with an accuracy floor | `llm-eval-harness` run id + date |
| Groundedness / faithfulness (RAG) | higher | weighted | eval run id + date |
| Public benchmark score | higher | low weight; only if it matches the task | benchmark name, version, date |
| p95 latency | lower | weighted; SLO as `hard_max` | load test on the target region/stack |
| Monthly cost | lower | weighted | dated price sheet + workload |
| Context window | higher | constraint (`hard_min`), weight 0 | vendor documentation, dated |
| Hosting (api / self-host) | — | constraint (`hard_in`) when policy requires | policy reference |
| Region / data residency | — | constraint (`hard_in`) | contract or DPA reference |

## Rules
1. **Must-haves are constraints, not weights.** A 0.9 weight on "self-host" still lets a strong API model win.
2. **Weights are a decision, owned by a role.** Record who set them; when sensitivity shows the winner flips, return to that owner.
3. **One measurement per idea.** Do not score both "accuracy" and a benchmark that measures the same capability.
4. **Same conditions for every candidate.** Same eval set, prompt, temperature and date; otherwise the comparison is void.
5. **Provenance on every row.** `source` and `as_of` per candidate; prices and benchmark results go stale quickly, so re-run when either changes.
6. **No facts from memory.** The skill never supplies prices, scores or capabilities; a missing fact is `[TO BE BASELINED — owner: <role>]`.

## Owners used by the script
| Gap | Owner role |
|---|---|
| Missing model fact, source or date | Model evaluation lead |
| Weights to confirm when the winner is sensitive, or constraints to relax when nothing survives | Solution architect |
