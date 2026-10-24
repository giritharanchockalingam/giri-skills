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

## Not done in this PR (named, not dropped)

- Live run of the acceptance check needs: migration 0025 applied to the shared Supabase project, `PORT_REGISTRY_REPO=giritharanchockalingam/giri-skills` set in Vercel, deploy of `main`, then **Push skills to Port** (or `POST /api/port/sync`) and `GET /api/port/reconcile?format=text`. Owner approval required for the first two (house rule 5); output goes in this PR before merge-to-main is considered done.
- The "1 retire test" retires a real published version, which is irreversible without the 4-gate protocol (new draft → eval → approve → publish). Proposal: retire the oldest superseded-free skill the owner names, confirm the entity flips to `retired`, then restore by publishing a new version of that skill through the normal gates. Owner picks the skill.
- `studio/tests/worker.test.mjs` fails on `main` before this change (2 failures, unrelated: delivery worker fixture) — not touched.
