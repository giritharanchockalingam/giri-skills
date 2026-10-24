# Skills Factory × Port — WP2: skill_quality scorecard

Spec §4.2 / §5.2. Bronze and Silver only; Gold is fenced by D3 and not created.

| Piece | Where |
|---|---|
| Scorecard definition, ensure (create / replace on drift / no-op), Port readback | `studio/lib/integrations/port/scorecard.ts` |
| Ensured in the outbox worker after the blueprint; operator route `GET /api/port/scorecard?slugs=` | `studio/lib/integrations/port/outbox.ts`, `studio/app/api/port/scorecard/route.ts` |
| Tests | `studio/tests/port-sync.test.ts` (scorecard case) |

Contract test subjects (from the factory's own data, 2026-10-24): `llm-cost-model` — healthy, approval valid → expected **Silver**; `perf-review-runner` — published, no eval row → `not-evaluated` → expected **Bronze**; `effort-estimator` — `being-improved` → expected **Bronze**.

Live readback (2026-10-24 01:19 UTC, `GET /api/port/scorecard`, scorecard `created` on this call; levels are Port's computation):

| slug | sf_eval_verdict | sf_approval_valid | Port level |
|---|---|---|---|
| llm-cost-model | healthy | true | **Silver** |
| perf-review-runner | not-evaluated | true | **Bronze** |
| effort-estimator | being-improved | true | **Bronze** |

Gold: not created (D3). Screenshot of an entity page: owner to attach to PR #158.
