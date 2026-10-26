# Brainstorm Fallback (when superpowers:brainstorming is not installed)

Goal: surface the questions whose answers change the plan, with a default for each, in one round.

## Method
1. Restate the request in one sentence as an outcome ("Users can export invoices as CSV per tenant").
2. Walk the dimension list below; for each, decide: known from SPEC/repo, assumed (state the default), or must ask.
3. Ask only the "must ask" items, max 5, each with your default so the user can reply "defaults".
4. Record answers at the top of the plan file under "Decisions".

## Dimensions
| Dimension | Question shape | Typical default |
|---|---|---|
| Users / roles | Who can do this? Which roles are excluded? | tenant admin + member; viewer read-only |
| Data | New tables or columns? Tenant-scoped? Retention? | new table with `tenant_id`, RLS, 90-day retention |
| Boundaries | Server action, route handler, or edge function? | server action for UI; route handler for external callers |
| Volume | Expected rows / requests / file sizes? | ≤10k rows per export; ≤5 MB |
| Failure | What happens on partial failure? Retry? Idempotent? | fail whole op, Result<E>, idempotency key on writes |
| Visibility | Flag-gated? Rollout per tenant? | flag `feature.<name>`, default off in prod |
| Audit | Must the action be in the audit log? | yes for any write to tenant data |
| Non-functional | Latency, a11y, i18n needs? | p95 ≤ 300 ms API; WCAG AA |
| Out of scope | What will reviewers assume is included but is not? | list explicitly |

## Anti-patterns
- Asking questions whose answer does not change the file table.
- Asking without a default (forces a round-trip).
- More than one round of questions.
