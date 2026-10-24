# Skills Factory × Port — handoff (2026-10-24)

| WP | What | Proof | Doc |
|---|---|---|---|
| 0 | Tenant discovery | inventory committed; D6a, D7b | PORT-INTEGRATION-WP0.md, PORT-TENANT-INVENTORY.md |
| 1 | Publish sync (outbox, sf_ props, reconcile) | 66/66 hash + state match | WP1 |
| 2 | `skill_quality` scorecard | Port-computed Silver/Bronze/Bronze; Gold added per D3 | WP2 |
| 3 | Run from Port, idempotent | same run on forced replay, 1 row | WP3 |
| 4 | Run on a PR + `sf_skill_run` evidence | run related to skill + repo | WP4 |
| 5 | Port MCP discovers, factory MCP runs (Cursor) | v2 = v2 | WP5 |
| 6 | PR review gate (§7 proof slice) | Reviewed → Not reviewed → Reviewed on PR #165; trace 3 clicks | WP6 |

## Operating it

| Task | How |
|---|---|
| Push skills to Port | Factory → Integrations → Port → **Push skills to Port** (admin) |
| Check factory vs Port | `curl -s -H "Authorization: Bearer $(cat ~/.sf-health-token)" "https://giri-skills-studio.vercel.app/api/port/reconcile?format=text"` |
| Drain the outbox / refresh MCP tools | `curl -s -X POST -H "Authorization: Bearer $(cat ~/.sf-health-token)" "https://giri-skills-studio.vercel.app/api/port/sync?mcp=1&workspace=7bd1fe59-6bba-44af-8848-ea6cb2f577ab"` |
| Scorecard readback | `curl -s -H "Authorization: Bearer $(cat ~/.sf-health-token)" "https://giri-skills-studio.vercel.app/api/port/scorecard?slugs=code-review-runner"` |
| Review a PR from Port | Workflows → **Run governed skill on a PR** → repository, PR number, skill |

## Open items

| Item | Owner | Note |
|---|---|---|
| Independent fresh-eyes read | Owner | Anyone who did not build it, from the Port page only |
| Retire test (live) | Owner | Skipped; unit-tested |
| Devin MCP | Owner | Web app Customize → MCPs (desktop location unconfirmed) |
| PR #165 | Owner | Reviewed; ready to merge |
| Port aggregation lag (~26 min) | Port | Tenant behaviour; factory state is immediate |
| `worker.test.mjs` 2 failures | Factory | Pre-existing on main before WP0 |
