---
name: mcp-server-builder
description: Use when the user asks to build, wrap, or review an MCP (Model Context Protocol) server — "expose our API as MCP tools", "build an MCP server for X", "review this MCP server". Produces a spec-compliant server (tools, resources, prompts) with JSON-schema tool contracts, auth and scoping, structured errors, tests, and a README. Delegates to the Anthropic mcp-builder skill when installed; otherwise follows the bundled spec essentials. Not for agent design (use agent-architecture) or for generic REST APIs.
license: MIT
metadata:
  domain: ai-platform
  version: 0.1.0
  author: giri-skills
---

# MCP Server Builder

## When to use
- Building a new MCP server (Python or TypeScript), wrapping an existing API/database/SaaS as MCP tools, or reviewing a server for spec compliance and safety.
- NOT for: choosing which tools an agent needs (`agent-architecture`), evaluation (`llm-eval-harness`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Target system(s) to expose and their API/docs | yes | user / repo / URL |
| Tool list with side-effect class (read / write / irreversible / external_comm) | yes | user; derive with `agent-architecture` if absent |
| Language and transport (stdio for local, Streamable HTTP for remote) | yes | user; default Python + stdio for local, Streamable HTTP for remote |
| Auth model (API key, OAuth, service account) and tenant model | yes | user |
| Consumers (Claude Desktop/Code, custom agent, gateway) | no | user |

If the target system or the tool list is missing, ask once.

## Procedure
1. Read `../../../shared/quality-bar.md`, `../../../shared/stack-conventions.md`, `../../../shared/token-efficiency.md`.
2. **Choose the implementation path.** If the Anthropic `mcp-builder` skill is installed (see `VENDORED.md` at the repo root), use it for scaffolding and SDK specifics; else follow `references/mcp-spec-essentials.md`, which is a complete fallback covering protocol primitives, tool schemas, transports, auth, errors, and testing.
3. **Design tool contracts first.** One JSON contract per tool using `assets/tool-contract.schema.json` (same template as `agent-architecture`). Apply the rules in `references/mcp-spec-essentials.md` §3: narrow tools, `additionalProperties: false`, enums, pagination, structured errors, side-effect metadata.
4. **Scaffold** per `references/server-skeleton.md`: layout, config, logging, health, tests. Keep business logic in a service layer; the MCP layer only validates, authorizes, calls, and shapes output.
5. **Implement auth and scoping.** Tenant and principal come from the transport auth context; never from tool arguments. Scope check per tool; deny by default.
6. **Harden.** Timeouts, rate limits, result size caps, untrusted-output labeling, no secrets in logs, no raw exception text to the model.
7. **Test** with `references/testing-checklist.md`: schema validation, authZ, error shapes, pagination, idempotency, injection corpus, protocol handshake via the SDK test client or the MCP Inspector.
8. **Document**: README with tool table (name, purpose, side effect, scopes), install/run, config, security notes.
9. Run the self-check.

## Output
- Server repo or directory: `src/`, `tests/`, `README.md`, `.env.example`, `tools/*.json` contracts.
- Tool table in the final reply (name | side effect | scopes | status).

## Self-check
- [ ] Every tool has input and output schemas, side-effect class, idempotency statement, timeout
- [ ] No `run_sql` / `execute_code` / `http_request` style generic tools unless sandboxed, allow-listed, and HITL-gated
- [ ] Tenant and principal derived from auth context only
- [ ] Errors are structured with enumerated codes; no stack traces to the model
- [ ] Tests cover schema, authZ, errors, pagination, injection
- [ ] README tool table matches the registered tools
- [ ] Secrets only via env; `.env.example` complete

## References
- `references/mcp-spec-essentials.md` — protocol, primitives, schemas, transports, auth, errors (fallback when mcp-builder is absent)
- `references/server-skeleton.md` — layout, config, logging, health
- `references/testing-checklist.md` — test matrix and tooling
- `assets/tool-contract.schema.json` — per-tool contract template
