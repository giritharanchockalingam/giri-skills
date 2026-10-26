# Error and Result Pattern

## Principle
Expected failures are values; unexpected failures are exceptions. Services return `Result<T, AppError>`; nothing throws across the server→client boundary.

## Types (`lib/result.ts`, see `assets/result.ts`)
```ts
export type Result<T, E = AppError> = { ok: true; value: T } | { ok: false; error: E };
export type AppError = {
  code: ErrorCode;            // stable, machine-readable
  message: string;            // safe to show the user
  status: 400|401|403|404|409|422|429|500;
  fieldErrors?: Record<string, string[]>;
  cause?: unknown;            // never serialized to client
};
```

## Error code catalogue (extend per domain)
| Code | Status | When |
|---|---|---|
| `VALIDATION_FAILED` | 422 | zod parse failed; `fieldErrors` filled |
| `AUTH_REQUIRED` | 401 | no session |
| `AUTH_FORBIDDEN` | 403 | role/tenant mismatch, RLS denial (`42501`) |
| `NOT_FOUND` | 404 | row missing or filtered by RLS (same response — do not leak existence) |
| `CONFLICT` | 409 | unique violation (`23505`), optimistic lock mismatch |
| `RATE_LIMITED` | 429 | limiter |
| `UPSTREAM_FAILED` | 502 | external API error after retries |
| `INTERNAL` | 500 | anything unmapped; logged with `requestId`; generic message |

## Mapping Postgres/Supabase errors (`lib/db/errors.ts`)
| PG code | AppError |
|---|---|
| `42501` | `AUTH_FORBIDDEN` (write) / `NOT_FOUND` (read) |
| `23505` | `CONFLICT` |
| `23503` | `VALIDATION_FAILED` (bad reference) |
| `23514` | `VALIDATION_FAILED` (check constraint) |
| `PGRST116` (0 rows with `.single()`) | `NOT_FOUND` |
| other | `INTERNAL` + log |

## Layer behaviour
| Layer | Does |
|---|---|
| `lib/db` | returns `Result`; maps PG errors; never throws for data conditions |
| `server/services` | composes; adds domain codes (`INVOICE_ALREADY_PAID`); logs at `warn` for 4xx, `error` for 5xx |
| `server/actions` | `toActionState(result)` → `{ ok, data?, error?: { code, message, fieldErrors } }` — strips `cause` |
| route handlers | `toResponse(result)` → `NextResponse.json({ error: { code, message } }, { status })` |
| components | render `error.message`; branch on `error.code` for UX (e.g. `CONFLICT` → refresh prompt) |
| `error.tsx` | catches only thrown (unexpected) errors; shows `requestId` for support |

## Rules
- Never `catch (e) { return fail('INTERNAL') }` without logging `e` and the `requestId`.
- Never return raw PG messages to clients.
- `NOT_FOUND` and `AUTH_FORBIDDEN` on reads look identical to the caller.
- Validation errors carry field paths from zod (`error.flatten().fieldErrors`).
- `Result` helpers: `ok(v)`, `fail(code, message, extra?)`, `isOk`, `unwrapOr`, `mapResult`.
- Don't nest `Result` inside `Result`; services flatten.
