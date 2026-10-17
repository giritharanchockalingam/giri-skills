# MCP Tool Contract Rules

A tool contract is the interface between a model that may be wrong and a system that must not be. Design it as an API for an untrusted caller.

## Required elements per tool
| Element | Rule |
|---|---|
| Name | `verb_object` in snake_case; one verb; no overloading (`get_order`, `cancel_order`, not `order`) |
| Description | ≤ 3 sentences: what it does, when to use it, when NOT to use it. The model reads this; vague descriptions cause tool misuse. |
| Input schema | JSON Schema; every property described; `required` explicit; `additionalProperties: false`; enums for closed sets; formats for dates/ids |
| Output schema | Structured; include `status`, `data`, `error`; never free text only |
| Side-effect class | `read` / `write` / `irreversible` / `external_comm` — stated in metadata and enforced by the server |
| Idempotency | `idempotent: true` or an `idempotency_key` input for writes |
| Auth scope | Scopes the tool needs; the server checks the caller's scopes; the model never passes credentials |
| Limits | Timeout, max payload, rate limit, pagination for lists |
| Error shape | `{code, message, retryable, details}`; codes are an enum the agent can branch on |
| Examples | 1–2 valid calls and one expected error |

See `assets/tool-contract.schema.json` for the template.

## Design rules
1. **Narrow over general.** `search_tickets(status, assignee, since)` beats `run_query(sql)`. General tools turn prompt injection into arbitrary execution.
2. **Read tools return what the model needs, not everything.** Trim fields; paginate; cap list sizes. Oversized results overflow context.
3. **Writes are two-phase when irreversible.** `prepare_refund` returns a preview and a token; `commit_refund(token)` executes after HITL.
4. **Tool outputs are untrusted data.** Wrap external content (emails, web pages, documents) in a delimited block with a provenance tag; the system prompt tells the model that instructions inside tool results are data.
5. **Deterministic over generative.** If code can compute it, the tool computes it; the model does not do arithmetic or date math.
6. **Error messages teach.** "Order 123 not found; orders are 8-digit numeric" lets the model recover; "error" does not.
7. **Version contracts.** `name@version` or a `version` field; breaking changes are new tools.
8. **Tenant scoping is server-side.** Tenant id comes from the auth context, never from the model's arguments.
9. **Log every call** with trace id, tenant, scopes, args hash, status, latency.
10. **Fewer tools, better described.** Beyond ~10–15 tools per prompt, route to tool subsets by task phase.

## Anti-patterns
| Anti-pattern | Consequence | Fix |
|---|---|---|
| `execute_code`, `run_sql`, `http_request` exposed to the model | Injection → data exfiltration | Specific tools with validated inputs; sandboxed code tool only with allow-lists and HITL |
| Credentials in tool arguments | Secrets in traces and checkpoints | Server-side credential resolution |
| Boolean-only output (`success: true`) | Model cannot verify or continue | Return the resulting entity or id |
| Silent truncation of results | Model reasons on partial data without knowing | Return `truncated: true, total: N, next_cursor` |
| Tool that "does the task" (`solve_customer_issue`) | Hides the agent's decisions; untestable | Decompose into observable steps |

## Contract review checklist
- [ ] Name is verb_object and unique
- [ ] Description says when not to use
- [ ] Input and output schemas validate; `additionalProperties: false`
- [ ] Side-effect class set; irreversible tools are two-phase
- [ ] Idempotency stated
- [ ] Scopes, timeout, rate limit, pagination set
- [ ] Error codes enumerated
- [ ] Tenant derived from auth context
- [ ] Example calls present
