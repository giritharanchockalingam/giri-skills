# MCP Server Testing Checklist

| # | Test | Pass criterion |
|---|---|---|
| 1 | Contract: each `tools/*.json` validates as JSON Schema; examples validate against inputSchema/outputSchema | All pass |
| 2 | Contract: extra properties rejected | `additionalProperties: false` enforced |
| 3 | `tools/list` returns exactly the documented tools with matching schemas | Diff is empty vs `tools/*.json` |
| 4 | Handshake: `initialize` → `initialized` → `tools/list` via SDK client | Succeeds; protocol version negotiated |
| 5 | AuthZ: missing scope → `FORBIDDEN`; missing principal → `UNAUTHORIZED` | No downstream call made |
| 6 | Tenant scoping: tenant in args is ignored; tenant from auth context used | Cross-tenant read returns NOT_FOUND |
| 7 | Validation: bad enum, bad id format, out-of-range limit → `INVALID_ARGUMENT` with a teaching message | Message names the rule |
| 8 | Pagination: `limit`, `cursor`, `truncated`, `next_cursor` | Full traversal reconstructs the set |
| 9 | Timeout: downstream slow → `TIMEOUT`, `retryable: true` | Within configured timeout + margin |
| 10 | Idempotency: repeated write with same key → single effect | Second call returns the first result |
| 11 | Two-phase: commit without prepare token → `INVALID_ARGUMENT`; expired token → `CONFLICT` | |
| 12 | Result caps: oversized result → truncated with flag | Bytes ≤ `MAX_RESULT_BYTES` |
| 13 | Injection corpus: tool results containing instructions are returned labeled untrusted and unchanged | No instruction execution path exists in server |
| 14 | SSRF/path: URL or path arguments outside allow-list rejected | |
| 15 | Logging: no secrets or raw PII in logs; trace id present | Log scan passes |
| 16 | stdio: nothing but JSON-RPC on stdout | Byte-level check |
| 17 | Rate limit: burst above limit → `RATE_LIMITED` | |
| 18 | Inspector manual pass: `npx @modelcontextprotocol/inspector` lists and calls each tool | Recorded in PR |

CI: lint → typecheck → unit (1–17) → integration against sandbox → package.
