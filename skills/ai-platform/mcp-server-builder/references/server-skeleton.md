# MCP Server Skeleton (Python default; TypeScript mirror noted)

## Layout
```
<server>/
├── README.md               tool table, install, config, security notes
├── pyproject.toml          pinned deps (mcp SDK, pydantic, httpx); ruff + pytest
├── .env.example            every variable documented
├── tools/                  one JSON contract per tool (source of truth for schemas)
├── src/<pkg>/
│   ├── server.py           registers tools/resources/prompts; transport entrypoint
│   ├── auth.py             principal + scopes from transport context; require_scopes()
│   ├── config.py           env parsing with validation at boot
│   ├── logging.py          structured JSON logs to stderr (stdio) or collector
│   ├── errors.py           error codes enum; to_tool_error()
│   ├── services/           domain logic; downstream clients with timeouts/retries
│   └── tools/              one module per tool: validate → authz → service → shape
└── tests/
    ├── test_contracts.py   schemas validate; examples pass
    ├── test_tools.py       handler behaviour with mocked services
    ├── test_protocol.py    handshake, list, call via SDK client
    └── test_security.py    injection corpus, oversized inputs, SSRF/path args
```
TypeScript mirror: `src/server.ts`, `src/auth.ts`, `src/tools/*.ts`, `tests/*.test.ts` (vitest), `zod` schemas generated from `tools/*.json` or vice versa.

## Config (.env.example)
```
MCP_TRANSPORT=stdio            # stdio | http
MCP_HTTP_HOST=127.0.0.1
MCP_HTTP_PORT=8080
LOG_LEVEL=info
DOWNSTREAM_BASE_URL=
DOWNSTREAM_TIMEOUT_MS=5000
DOWNSTREAM_API_KEY=            # local only; remote servers resolve per-tenant from vault
RATE_LIMIT_PER_MIN=60
MAX_RESULT_BYTES=65536
```

## Logging fields
`ts, level, msg, trace_id, principal_id, tenant_id, tool, status, latency_ms, error_code` — never raw arguments that may hold secrets or PII; log an argument hash instead.

## Health and ops
- `GET /healthz` (HTTP transport) returns build version and downstream reachability.
- Graceful shutdown on SIGTERM; in-flight calls finish or time out.
- Version in `initialize` server info; changelog per tool version.

## README tool table
| Tool | Purpose | Side effect | Scopes | Idempotent |
|---|---|---|---|---|
