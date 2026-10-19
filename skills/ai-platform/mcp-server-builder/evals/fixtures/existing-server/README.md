# ticket-mcp

Minimal MCP-style server (JSON-RPC 2.0 over stdio, Python stdlib). Fictional fixture: the server as deployed today; `search_tickets` is implemented, `read_ticket` is a stub.

## Tools
| Tool | Purpose | Side effect | Status |
|---|---|---|---|
| `search_tickets` | Search support tickets by status and date. Use before reading or updating a ticket. | read | implemented |
| `read_ticket` | Read one ticket by id. | read | stub |

## Run
```
python3 server.py
```
One JSON-RPC message per line on stdin; responses on stdout; nothing else is written to stdout.

## Test
```
python3 -m pytest -q tests
```

## Next steps
1. Implement each handler in `server.py` against its contract in `tools/<name>.json` (source of truth).
2. Add auth/scoping from the transport context (never from arguments), timeouts, rate limits, result caps.
3. Work through `references/testing-checklist.md` in the mcp-server-builder skill.

Sample data only; no credentials are read or stored by the scaffold.
