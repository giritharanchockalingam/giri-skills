# Log Schema

One JSON object per line to stdout. Vercel captures stdout; Log Drains forward it.

## Fields
| Field | Type | Required | Source |
|---|---|---|---|
| `ts` | ISO 8601 UTC | always | logger |
| `level` | `debug`/`info`/`warn`/`error` | always | caller |
| `msg` | string, static phrase | always | caller — "invoice created", never `invoice ${id} created` |
| `service` | `web` / `edge-fn:<name>` / `job:<name>` / `script:<name>` | always | env `SERVICE_NAME` or default `web` |
| `env` | `production` / `preview` / `development` | always | `VERCEL_ENV` ?? `NODE_ENV` |
| `version` | git sha | always | `VERCEL_GIT_COMMIT_SHA` |
| `requestId` | string | request scope | middleware (`x-request-id` or generated) |
| `vercelId` | string | request scope | `x-vercel-id` header |
| `userId` | uuid | when known | `requireUser()` |
| `tenantId` | uuid | when known | `requireUser()` |
| `route` | string | request scope | pathname pattern, not raw URL |
| `action` | string | server actions / jobs | `invoice.create` |
| `outcome` | `ok` / `<ERROR_CODE>` | operations | Result mapping |
| `durationMs` | number | operations | caller |
| `err` | `{ name, message, code?, stack? }` | errors | serializer; stack only at `error` level |
| context | flat key/values | optional | ids, enums, counts only |

## Levels
| Level | Use | Prod volume target |
|---|---|---|
| `debug` | development tracing | off in prod (`LOG_LEVEL=info`) |
| `info` | state changes: created/updated/deleted/sent; request completed | 1–3 lines per request |
| `warn` | expected failures: validation, 401/403/404/409, retry succeeded | — |
| `error` | unexpected: 5xx, upstream down after retries, invariant broken | every one is actionable |

## Redaction (applied by the logger before serialization, case-insensitive key match)
`password, passwd, secret, token, authorization, cookie, set-cookie, apikey, api_key, key, email, phone, ssn, card, iban, dsn` → value replaced by `"[redacted]"`. Nested objects walked to depth 5. Strings > 2 kB truncated with `…[+N]`.

## Request context (`lib/logger/context.ts`)
- `AsyncLocalStorage<{ requestId, vercelId, userId?, tenantId?, route }>`.
- `middleware.ts` generates/propagates `x-request-id` and sets it on the response.
- `requireUser()` enriches the store with `userId`, `tenantId`.
- `log.info(ctx, msg)` merges store + ctx automatically; services never pass ids by hand.

## Rules
| Rule | Enforcement |
|---|---|
| `no-console: error` | ESLint |
| No raw request bodies, headers, or URLs with query strings | review; redaction catches common keys |
| Error logged once, at the handling layer | review |
| Log line per outcome, not per step | review |
| Pretty output only when `NODE_ENV=development && LOG_PRETTY=1` | logger |

## Finding a request
1. User reports → ask for `requestId` shown on the error page.
2. Log sink query: `requestId:"<id>"` → all lines across web + edge + jobs.
3. Error tracker: tag `requestId` → event with stack.
