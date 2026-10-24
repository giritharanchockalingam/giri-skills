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

Live output: _to be appended_.
