# Logging Conventions

## Schema (one JSON object per line)
| Field | Type | Required | Notes |
|---|---|---|---|
| `ts` | ISO 8601 | yes | |
| `level` | debug/info/warn/error | yes | |
| `msg` | string | yes | static phrase, no interpolated ids ("invoice created", not `invoice ${id} created`) |
| `requestId` | string | yes (request scope) | from `x-request-id` header or `crypto.randomUUID()`; Vercel sets `x-vercel-id` — include both |
| `userId` | uuid | when known | |
| `tenantId` | uuid | when known | |
| `service` | string | yes | `web`, `edge-fn:<name>`, `job:<name>` |
| `env` | string | yes | `VERCEL_ENV` or `development` |
| `durationMs` | number | for operations | |
| `err` | `{ name, message, stack?, code? }` | on error | stack only in non-prod or at `error` level |
| `...context` | key/values | optional | ids and enums only |

## Rules
| Rule | Why |
|---|---|
| `lib/logger` only; `console.*` banned by ESLint (`no-console`) | consistent schema |
| Child loggers per request: `logger.child({ requestId, userId, tenantId })` created in `requireUser()` / middleware | correlation without threading args |
| No PII in logs: no emails, names, free text, tokens, full URLs with query strings | compliance; redaction list in `logger.ts` |
| Level discipline | `debug` dev only; `info` state changes; `warn` expected failures (4xx); `error` unexpected (5xx) |
| One log line per operation outcome, not per step | cost and noise |
| Errors logged once, at the layer that handles them | no duplicate stacks |
| Server actions log `{ action, outcome, durationMs }` | audit of mutations at app level (DB audit covers data) |
| Never log request bodies | secrets and PII |

## Correlation
1. `middleware.ts`: read `x-request-id` or generate; set on request headers and response.
2. `requireUser()`: build child logger with ids; store in `AsyncLocalStorage` (`lib/logger/context.ts`) so services call `log()` without parameters.
3. Client errors (`error.tsx`) display `requestId`; support searches logs by it.

## Where logs go
- Vercel: stdout JSON → Log Drains (to the chosen sink). Configure in `observability-setup`.
- Supabase Edge Functions: `console.log(JSON.stringify(...))` via the same schema (separate tiny logger).
- Local: pretty-print only when `NODE_ENV=development` and `LOG_PRETTY=1`.
