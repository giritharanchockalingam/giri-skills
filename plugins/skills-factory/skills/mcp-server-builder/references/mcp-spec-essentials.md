# MCP Spec Essentials (fallback when the Anthropic mcp-builder skill is not installed)

Scope: enough of the Model Context Protocol to build a compliant, safe server without the vendored skill. Verify details against the current specification at modelcontextprotocol.io and the SDK version in use; protocol revisions change capability names and transport details.

## 1. Model
| Concept | Definition |
|---|---|
| Host | The application that embeds the model (Claude Desktop/Code, a custom agent) |
| Client | Protocol client inside the host; one client per server connection |
| Server | Your process; exposes tools, resources, prompts over JSON-RPC 2.0 |
| Transport | stdio (local child process) or Streamable HTTP (remote; HTTP POST + optional SSE stream). Older servers used HTTP+SSE; prefer Streamable HTTP for new work |
| Lifecycle | `initialize` (capability negotiation, protocol version) → `notifications/initialized` → normal operation → shutdown |

## 2. Primitives
| Primitive | Direction | Purpose | Key methods |
|---|---|---|---|
| Tools | Model-invoked | Actions and queries | `tools/list`, `tools/call`, `notifications/tools/list_changed` |
| Resources | Application/user-selected | Read-only data by URI (files, records, docs) | `resources/list`, `resources/read`, `resources/templates/list`, subscribe/updated |
| Prompts | User-selected | Reusable prompt templates with arguments | `prompts/list`, `prompts/get` |
| Sampling | Server → client | Server asks the host's model to complete something | `sampling/createMessage` (host may deny) |
| Roots | Client → server | Filesystem/URI boundaries the server should respect | `roots/list` |
| Logging | Server → client | Structured log notifications | `logging/setLevel`, `notifications/message` |
| Progress / cancellation | Both | Long operations | `notifications/progress`, `notifications/cancelled` |

Design rule: use **tools** for anything the model should decide to call; **resources** for context the user or app attaches; **prompts** for workflows a user picks by name.

## 3. Tool definition rules
A tool is `{ name, description, inputSchema, outputSchema?, annotations? }`.
| Element | Rule |
|---|---|
| `name` | `verb_object`, snake_case, unique, stable |
| `description` | What, when, when-not. ≤ 3 sentences. The model's only guide to correct use |
| `inputSchema` | JSON Schema object; `additionalProperties: false`; every property described; enums; formats; limits (`maximum`, `maxLength`) |
| `outputSchema` | Declare when returning structured content; return `structuredContent` matching it plus a text fallback |
| `annotations` | Hints: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`. Hints are advisory; enforce the real policy server-side |
| Result | `content: [{type: "text" | "image" | "resource", ...}]`, `isError: boolean`. Tool-level failures are `isError: true` with a structured message; protocol failures are JSON-RPC errors |

Error payload convention (put in the text/structured content):
```json
{"code": "NOT_FOUND", "message": "Order 12345678 not found; order ids are 8 digits", "retryable": false}
```
Codes: `INVALID_ARGUMENT, NOT_FOUND, UNAUTHORIZED, FORBIDDEN, RATE_LIMITED, TIMEOUT, CONFLICT, UPSTREAM_ERROR, INTERNAL`.

Design rules (from `agent-architecture/references/mcp-tool-contracts.md`):
1. Narrow tools over generic executors.
2. Paginate and cap results; return `truncated`, `total`, `next_cursor`.
3. Two-phase (prepare/commit) for irreversible actions.
4. Label untrusted third-party content in results.
5. Tenant/principal from auth context, never from arguments.
6. Version tools; breaking change = new tool.

## 4. Transport and deployment
| Transport | Use | Notes |
|---|---|---|
| stdio | Local tools for a desktop host or CLI | Server reads JSON-RPC from stdin, writes to stdout; **never write logs to stdout** — use stderr |
| Streamable HTTP | Remote/shared servers; multi-tenant | Single endpoint; POST for requests, optional SSE for server→client streams; session id header; must handle resumability and origin validation |

Remote servers: TLS only; validate `Origin`; bind to localhost when meant to be local; rate limit per principal; health endpoint outside the MCP path.

## 5. Authorization
| Scenario | Approach |
|---|---|
| Local stdio | Inherit the user's environment; credentials via env vars; no network auth |
| Remote HTTP | OAuth 2.1 per the MCP authorization spec: server is a resource server; tokens validated per request; scopes map to tools. Support dynamic client registration and protected-resource metadata where the spec requires |
| Service-to-service | Bearer token or mTLS at the gateway; map to a principal and scopes |
| Downstream credentials | Held by the server (vault/env); never passed through tool arguments; per-tenant credential lookup by principal |

Scope model: `resource:action` (e.g., `tickets:read`, `tickets:write`). Each tool declares required scopes; deny by default; log every denial.

## 6. Security checklist
- [ ] No generic execution tools unless sandboxed, allow-listed, and gated
- [ ] Input validation on every argument beyond JSON Schema (ids, ranges, path traversal, SSRF targets)
- [ ] Output caps (bytes, items); secrets and PII redacted per policy
- [ ] Untrusted content delimited and labeled (`untrusted_output: true` in contract)
- [ ] Timeouts on all downstream calls; circuit breaker for flaky dependencies
- [ ] Structured logs to stderr/collector with trace id, principal, tool, status, latency; no arguments containing secrets
- [ ] Rate limits per principal and per tool
- [ ] Dependency pinning; SBOM if the org requires it

## 7. Minimal server shape (Python, conceptual)
```python
# SDK names vary by version; this shows the responsibilities, not exact imports.
server = Server("tickets-mcp")

@server.tool(name="search_tickets", description="Search support tickets by status, assignee, and date. Use before reading or updating a ticket. Do not use to create tickets.")
def search_tickets(status: Status, assignee: str | None = None, since: date | None = None, limit: int = 20, cursor: str | None = None) -> ToolResult:
    principal = auth_context()                     # from transport, never from args
    require_scopes(principal, ["tickets:read"])
    page = ticket_service.search(principal.tenant_id, status, assignee, since, limit, cursor)  # timeout inside service
    return ok({"items": page.items, "total": page.total, "truncated": page.truncated, "next_cursor": page.next})
```
Responsibilities per tool handler: authZ → validate → call service with timeout → shape output → log. Nothing else.

## 8. Testing
| Level | What | How |
|---|---|---|
| Contract | Schemas validate; examples pass; `additionalProperties` rejected | JSON Schema validator in unit tests |
| Handler | authZ denial, invalid args, not found, upstream timeout, pagination | pytest with mocked service |
| Protocol | initialize handshake, `tools/list`, `tools/call`, error shapes | SDK test client or MCP Inspector (`npx @modelcontextprotocol/inspector`) |
| Security | Injection corpus in tool outputs; SSRF/path traversal args; oversized inputs | Dedicated test module |
| Integration | Against a sandbox of the downstream system | CI job with secrets from the CI vault |

## 9. Interop notes
| Host | Config |
|---|---|
| Claude Desktop / Claude Code | Add the server to the host's MCP config (command + args for stdio, or URL for HTTP). Verify with the host's MCP status view |
| Custom agent (LangGraph) | Use an MCP client adapter to load tools; map MCP tool contracts to the agent's tool list; keep per-phase tool subsets |
| Gateway | Many enterprises front MCP servers with a gateway for auth, logging, and allow-lists; design the server to be stateless per request where possible |
