# Plan Method — from spec to task-gated plan

## Gate definitions
| Gate | Entry | Exit evidence |
|---|---|---|
| plan | spec/ticket + repo read | `docs/plans/<slug>.md` with file table, tasks, risks, rollback |
| approve | plan posted | explicit "go" from the user (or "go with changes: …") |
| build | task N started | diff limited to task N's file list |
| test | task N code done | task N tests pass AND full unit suite passes |
| verify | all tasks done | lint + typecheck + unit + build green; e2e on touched paths; acceptance criteria ticked |
| handoff | verify done | HANDOFF.md updated with changed files + next prompt |

A gate without its exit evidence is not passed. "Should work" is not evidence.

## Task decomposition rules
| Rule | Why |
|---|---|
| One task = one vertical slice that can be tested alone | keeps diffs reviewable, lets a thread stop safely mid-plan |
| Order: schema → validators → services → actions/routes → UI → e2e | each layer tests against the one below |
| Max 8 tasks per plan; more → split into two plans (two threads) | token budget and review quality |
| Size S (≤1 h), M (≤half day), L (≤1 day). No XL — split it | estimate honesty |
| Schema tasks delegate to `supabase-schema-rls`; auth-touching tasks add a `security-review` task | specialist skills own their domain |
| Every task names its rollback | no task is "unrevertable" |

## File table format
| Path | Action | Why | Risk |
|---|---|---|---|
| `supabase/migrations/0007_invoices.sql` | create | invoices table + RLS | schema |
| `server/validators/invoice.ts` | create | zod schema | — |
| `server/services/invoice.ts` | create | create/list; Result<T,E> | — |
| `app/(app)/invoices/page.tsx` | create | server component list | — |

Read every "modify" file before listing it. If a file is listed from memory, the plan is wrong.

## Acceptance criteria rules
- Observable, binary, written as "Given / When / Then" or "Returns X when Y".
- Mapped 1:1 to at least one test. A criterion with no test is `[TO BE BASELINED — owner: ___]`.
- Non-functional criteria (latency, RLS, a11y) are stated per task when relevant, not deferred to "later".

## Test list rules
| Layer | Tool | When mandatory |
|---|---|---|
| Unit | vitest | every service, validator, util |
| Integration | vitest + local Supabase | every `lib/db` query, every RLS policy (positive and negative case) |
| E2E | playwright | every user-visible critical path the task adds or changes |
| Contract | zod parse tests | every external payload |

## Risk table
| Risk | Likelihood (L/M/H) | Impact (L/M/H) | Mitigation | Owner |
|---|---|---|---|---|
| Migration locks large table | M | H | add column nullable, backfill in batches | ___ |

Always consider: schema change, data backfill, auth/RLS, external API, feature flag default, env var, breaking type change.

## Rollback patterns
| Change type | Rollback |
|---|---|
| Code only | redeploy previous tag (`vercel rollback` or re-run prod.yml on previous tag) |
| Additive migration | leave schema; redeploy previous code; schedule drop migration |
| Destructive migration | forbidden without a two-step (expand → migrate → contract) plan across two releases |
| Flag-gated feature | set flag off; no deploy needed |
| External integration | disable integration via env; queue retries |

## Plan summary (what goes in chat)
```
Plan: <slug> — <N> tasks, est <S/M/L total>, touches <k> files
Schema: yes/no   Auth: yes/no   Flag: <name or none>
Risks: <top 2 with mitigation>
Rollback: <one line>
Full plan: docs/plans/<file>
Reply "go" to build, or "go with changes: …".
```
