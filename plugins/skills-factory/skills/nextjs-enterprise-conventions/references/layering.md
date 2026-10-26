# Layering and Naming

## Layers (import direction: top imports from below only)
```
app/ (routes, pages)  ──►  components/  ──►  server/actions/  ──►  server/services/  ──►  lib/db/  ──►  lib/supabase/
                                                 │                      │
                                                 └─► server/validators/ ◄┘
lib/utils, lib/logger, lib/result, lib/env: importable from any layer (pure, no I/O except logger)
```
| Layer | Owns | Must not |
|---|---|---|
| `app/**` | routing, layouts, composing components, calling services in RSC | contain business logic; call Supabase directly |
| `components/ui` | primitives (button, dialog, table) — no domain knowledge | import from `server/` or `lib/db` |
| `components/features/<domain>` | domain UI, hooks, client forms that call actions | call Supabase; contain authz logic |
| `server/actions` | thin: parse → auth → service → map → revalidate | contain queries or business rules |
| `server/services/<domain>` | business rules, orchestration, transactions, audit writes; returns `Result` | know about HTTP, FormData, React |
| `server/validators` | zod schemas + inferred types, shared by actions and services | import services |
| `lib/db` | typed queries (one file per entity), `types.ts` generated | business rules; multiple entities' rules |
| `lib/supabase` | `server.ts` (cookie client), `browser.ts` (anon), `admin.ts` (service role; `server-only`) | be imported by components (except browser.ts for auth UI) |

## Naming
| Thing | Convention | Example |
|---|---|---|
| Files | kebab-case | `invoice-table.tsx`, `create-invoice.ts` |
| Components | PascalCase, named export, one per file | `export function InvoiceTable()` |
| Server actions | verbObject | `createInvoice`, `voidInvoice` |
| Services | `<domain>.service.ts` exporting an object or functions | `invoiceService.create()` |
| Queries | `<entity>.ts` in `lib/db`, functions `getX / listX / insertX / updateX` | `listInvoicesByTenant()` |
| Validators | `<entity>.ts` exporting `XInput`, `xInputSchema` | `createInvoiceSchema` |
| Error codes | `SCREAMING_SNAKE`, domain-prefixed | `INVOICE_NOT_FOUND`, `AUTH_FORBIDDEN` |
| Env vars | `SCREAMING_SNAKE`; `NEXT_PUBLIC_` only for browser-safe | `SUPABASE_SERVICE_ROLE_KEY` |
| Tests | mirror path under `tests/unit`, `.test.ts` | `tests/unit/server/services/invoice.test.ts` |
| Feature flags | `feature.<name>` | `feature.invoice_export` |

## Auth helpers (`server/auth.ts`)
```ts
export async function requireUser(): Promise<Result<SessionUser, AppError>>   // 401
export async function requireRole(min: Role): Promise<Result<SessionUser, AppError>> // 403
```
`SessionUser = { id, tenantId, role, email }` built from `app_metadata`. Every action/route starts with one of these.

## Transactions and side effects
- Multi-table writes go through one service function; use a Postgres function (`rpc`) when atomicity is required — Supabase JS has no client-side transactions.
- Side effects (email, webhooks) are enqueued (`jobs` table or queue), never awaited inline in an action.
- Audit log write happens in the service, same call as the mutation.
