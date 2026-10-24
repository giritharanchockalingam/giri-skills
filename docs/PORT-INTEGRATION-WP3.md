# Skills Factory × Port — WP3: run a skill from Port, closed loop

Spec §5.3 / §6.2, under D6a (the live **Run governed skill** workflow, sync webhook, stays the closed loop; classic-action reporting via run logs/PATCH remains in the receiver for orgs that have classic actions).

## Shipped

| Requirement | Where / how |
|---|---|
| Shared-secret verification | Already stronger than the spec: Port HMAC signature (5-min window) or a workspace `sf_live_` bearer kept as the Port secret `SF_API_KEY` |
| Reject unknown action identifiers | Bodies now carry `action`; `KNOWN_ACTIONS` allow-list; unknown → 400, missing → accepted and logged (legacy workflow JSON) — `app/api/port/actions/route.ts`, `lib/integrations/port/map.ts` |
| 1 MiB body cap | > 1 MiB → 413 (was: silently truncated) |
| Idempotency on Port runId | Existing: `port:<runId>` is the factory idempotency key; a replay returns the same `run_id` with `deduplicated: true` in the sync reply |
| Factory run shows the Port runId | Run page labels the key as **Port run** |
| Run reporter | Sync reply carries status, checks, `run_id`, `port_run_id`, factory link (shown in the Port workflow run); classic path logs + PATCH unchanged |
| Approval-gated skills | Unchanged: the run parks at the factory gate; never auto-approved |

Owner action after merge: re-import the workflow JSON from Integrations → Port (adds `action` and `requested_by` to the body).

## Acceptance (spec WP3) — to run live

1. In Port, run **Run governed skill** on `code-review-runner` with its sample inputs → workflow run shows SUCCESS and the factory link; the factory run page shows "Port run <id>".
2. Forced duplicate: replay the same body (same `port_run_id`) to `/api/port/actions` with the `SF_API_KEY` bearer → reply has the **same** `run_id` and `deduplicated: true`; `sf_runs` has exactly one row with that key.

## Live acceptance (2026-10-24 01:59–02:04 UTC)

| Check | Result |
|---|---|
| Run from Port (workflow `run_governed_skill`, run `wfr_Rkf7AtnzJ9HFrluU`, skill `code-review-runner`, input = the skill's own eval fixture `change-risky.patch`) | HTTP 200 → factory run `807815d7-8d45-49fd-97a3-af023f477cd7`, link back to the factory, verdict BLOCK (status `failed`, 5/6 checks — the expected result for that diff) |
| Forced duplicate (same `port_run_id`, replayed to `/api/port/actions`) | same `run_id`, `deduplicated: true` |
| One factory run per Port run | `sf_runs` where `idempotency_key = 'port:wfr_Rkf7AtnzJ9HFrluU'` → **1** |

Found live and fixed in code: the copyable workflow identifier didn't match the org's (#160); a workspace key passed as `port_run_id` was stored as an idempotency key — the receiver now refuses key-shaped run ids (#161). The exposed key was revoked and replaced in Port's `SF_API_KEY` by the owner.
