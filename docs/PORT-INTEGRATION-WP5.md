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

## Acceptance (spec WP5)

In Claude Code:
1. "Using Port, what approved skills can review a PR for giri-skills? Include each skill's version, eval verdict and scorecard level." → answer from Port entities (expected to include `code-review-runner` v2).
2. "Run code-review-runner from the skills-factory MCP on this diff: <diff>" → factory run id; its version must equal the version Port reported.

Live output: _to be appended_.
