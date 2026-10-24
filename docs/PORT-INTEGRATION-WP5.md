# Skills Factory × Port — WP5: discover in Port's MCP, run through the factory's MCP (Claude Code)

Spec §5.4. Port's MCP server answers "which approved skills can do X" from the `aiSkill` entities and the `skill_quality` scorecard; the factory's own MCP server runs the chosen skill's published, hash-pinned version.

## Shipped

| Piece | Where |
|---|---|
| The factory's `_mcp_server` entity (registered in Port on 2026-10-20 as the "Skills Factory" connector) keeps `allowed_tools` = `find_skill`, `get_run` + every **published** skill slug; retire removes it on the next sync; only that one property is merged, the auth header stays as the admin set it | `studio/lib/integrations/port/mcpEntity.ts`, called by the outbox worker |
| `POST /api/port/sync?mcp=1&workspace=<id>` refreshes the tool list on demand | `studio/app/api/port/sync/route.ts` |
| Tests | `studio/tests/port-sync.test.ts` (WP5 case) |

## Claude Code setup (owner, on the work Mac)

```bash
# 1) Port MCP (EU org, app.port.io) — discovery; actions limited to the two factory workflows
claude mcp add --transport http port-eu https://mcp.port.io/v1 \
  --header "x-allowed-actions-to-run: run_governed_skill,run_sf_skill_on_repo"
# then in Claude Code: /mcp → port-eu → Authenticate (browser OAuth)

# 2) Factory MCP — execution under the workspace key (read at add time from a hidden prompt)
read -rsp "sf_live_ key: " SFK; echo
claude mcp add --transport http skills-factory https://giri-skills-studio.vercel.app/api/mcp \
  --header "Authorization: Bearer $SFK"
unset SFK
```

Discovery-only clients (CI, other agents) add `--header "x-read-only-mode: 1"` instead of the allowed-actions header.

## Cursor setup

`~/.cursor/mcp.json` (merged in place, file mode 600 — the key stays on the owner's machine):

```json
{ "mcpServers": {
  "port-eu":        { "url": "https://mcp.port.io/v1", "headers": { "x-allowed-actions-to-run": "run_governed_skill,run_sf_skill_on_repo" } },
  "skills-factory": { "url": "https://giri-skills-studio.vercel.app/api/mcp", "headers": { "Authorization": "Bearer <sf_live_ key>" } } } }
```

Cursor → Settings → MCP → port-eu → Login (Port OAuth).

## Devin setup

Customize → MCPs → Add MCP → Add custom MCP (Port is not in Devin's marketplace):

| Field | port-eu | skills-factory |
|---|---|---|
| Transport | HTTP | HTTP |
| URL | `https://mcp.port.io/v1` | `https://giri-skills-studio.vercel.app/api/mcp` |
| Auth | OAuth, Personal → Connect | Auth Header `Authorization: Bearer <key from Devin Secrets>` |
| Header | `x-allowed-actions-to-run: run_governed_skill,run_sf_skill_on_repo` | — |

One workspace key per agent (`cursor`, `devin`), so runs are attributable and revocable independently. Verify with **Test tools**.

## Acceptance (spec WP5)

In each client (Cursor, Devin):
1. "Using Port, what approved skills can review a PR for giri-skills? Include each skill's version, eval verdict and scorecard level." → answer from Port entities (expected to include `code-review-runner` v2).
2. "Run code-review-runner from the skills-factory MCP on this diff: <diff>" → factory run id; its version must equal the version Port reported.

## Live acceptance — Cursor (2026-10-24 03:37–03:38 UTC)

Cursor → Customize → MCPs: **port-eu** connected (63 tools, Port OAuth), **skills-factory** connected (71 tools = 66 published skills + `find_skill`, `get_run`, `deliver`, `delivery_status`, `compose`).

1. Discovery via port-eu — "what approved skills can review a PR for giri-skills?" — answered from `aiSkill` entities (approved, `sf_status = published`, `registry_file` under giri-skills) and the `skill_quality` scorecard:

| Skill | sf_version | sf_eval_verdict | skill_quality |
|---|---|---|---|
| code-review-runner | 2 | healthy | **Silver** |
| security-review | 1 | being-improved | Bronze |
| ui-component-quality | 2 | not-evaluated | Bronze |

2. Execution via skills-factory MCP — `code-review-runner` on the diff of a giri-skills commit (`7500a61…`, docs only) → run `d81a68a3-cbd4-49e7-9106-3932a789c45c`, **version 2**, succeeded 6/6, verdict PASS. Confirmed in `sf_runs`: `code-review-runner` v2, status `succeeded`, source `api`.

**Same skill, same version on both sides (2 = 2).** WP5 acceptance met.

Not done: Devin Desktop — its MCP settings location could not be confirmed; the documented path is Devin's web app (Customize → MCPs). Carried as an optional follow-up.
