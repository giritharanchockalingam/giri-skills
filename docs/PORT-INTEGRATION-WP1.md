# Skills Factory × Port — WP1: publish sync

Spec §5.1 (outbox), §6.1 (token), §6.3 (reconcile), §6.5 (retire). Decisions applied: D6a (workflow stays), D7b (`aiSkill` extended with `sf_` properties and related to Port's `skill` registry; `sf_skill` not created).

## Shipped

| Piece | Where |
|---|---|
| Outbox + links tables, publish/retire trigger, `sf_port_enqueue_all`, owner lookup | `studio/supabase/migrations/0025_sf_port_sync.sql` |
| `sf_` properties + registry relation on the blueprint; entity mapping; verdict mapping | `studio/lib/integrations/port/map.ts` |
| Blueprint extension in place (PATCH adds only what is missing); single-flight token | `studio/lib/integrations/port/client.ts` |
| Loader for published/retired skills (repo eval harness → verdict/trigger/lift; DB release state → approval, cases, model, time) | `studio/lib/integrations/port/sync.ts` |
| Worker with backoff/dead-letter; kick after publish/retire; operator routes `/api/port/sync`, `/api/port/reconcile` | `studio/lib/integrations/port/{outbox,kick,reconcile,serverAuth,env,state}.ts`, `studio/app/api/port/{sync,reconcile}/route.ts` |
| Integrations page: outbox state + dead letters; "Push skills to Port" = enqueue all → drain → reconcile | `studio/app/integrations/*` |
| Tests (mapping, blueprint PATCH, single-flight, auth, worker happy/failure paths, reconcile) | `studio/tests/port-sync.test.ts` |

Deviations from the spec text, all deliberate: entity identifier stays the bare slug (23 live entities keep their history; the `<workspace>__` prefix is multi-tenant, out of scope v1); `sf_version` is the factory's integer version as a string; `sf_eval_at` is the DB eval-run time (the repo harness publishes a date range, not an instant — left null rather than invented); the WP1 count is 66, not 23 (WP0 F2).

## Live acceptance (2026-10-24 01:01 UTC, owner's tenant)

```
POST /api/port/sync  → picked 50 synced 50 · picked 16 synced 16 · failed 0 · dead-lettered 0
Port reconcile @ 2026-10-24T01:01:35.725Z
factory: published=66 retired=0
port:    published=66 retired=0 total=66
outbox:  pending=0 failing=0 dead-lettered=0
matched (hash+status): 66 of 66
published-in-factory == published-in-port: YES
hash match on all: YES
```

What the first live run taught (all kept in code, none in data): Port caps blueprint descriptions at 200 chars (#157); the session middleware must exempt the bearer-protected operator routes (#156); `HEALTH_CHECK_TOKEN` is held only by the owner (rotated by him). The outbox behaved as specified throughout: 66 rows failed attempt 1 with Port's real 422 text, backed off, and drained clean after the fix — no row was hand-edited or dropped.

Follow-ups filed from this run: reconcile should default to the only workspace with published skills instead of refusing on "several workspaces"; sync drains 50 per call (two calls for a full backfill).

## Not done in this PR (named, not dropped)

- ~~Live run~~ done above (migration 0025 applied, `PORT_REGISTRY_REPO` set, both approved by the owner).
- The "1 retire test" retires a real published version, which is irreversible without the 4-gate protocol (new draft → eval → approve → publish). Proposal: retire the oldest superseded-free skill the owner names, confirm the entity flips to `retired`, then restore by publishing a new version of that skill through the normal gates. Owner picks the skill.
- `studio/tests/worker.test.mjs` fails on `main` before this change (2 failures, unrelated: delivery worker fixture) — not touched.
