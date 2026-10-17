# Test Pyramid per Feature Type

## Layers
| Layer | Tool | Runs against | Speed | Mocks |
|---|---|---|---|---|
| Unit | vitest | pure functions, validators, services with `lib/db` mocked | ms | `lib/db/*`, external clients |
| Integration | vitest (node env) | `lib/db` + RLS against local Supabase; services end-to-end with real DB | s | external HTTP only |
| Contract | vitest | zod schemas vs recorded payloads (webhooks, 3rd-party APIs) | ms | none |
| Component | vitest + @testing-library/react (jsdom) | client components with logic | ms | server actions |
| E2E | playwright | real app on preview/local, real DB | 10s+ | none (test accounts) |

Shape: many unit, some integration, few e2e. Rule of thumb per feature: 5–15 unit, 2–6 integration, 1–2 e2e.

## By feature type
| Feature type | Unit | Integration | Contract | Component | E2E |
|---|---|---|---|---|---|
| Validator (`server/validators`) | valid, each invalid field, boundary values | — | — | — | — |
| Service (`server/services`) | each rule branch; each error code; audit written | happy path with real DB; RLS-denied path | — | — | — |
| Query (`lib/db`) | — | returns expected rows; tenant filter; PG error mapping | — | — | — |
| Server action | parse failure → fieldErrors; auth failure; success maps result; revalidate called | — | — | — | via page e2e |
| Page / flow | — | — | — | client form states (pending, error) | critical path: load, act, assert, negative role |
| API route (webhook) | signature verify; bad payload | — | recorded payloads parse | — | optional |
| Edge function | handler logic with injected client | against local functions serve | — | — | — |
| Migration / RLS | — | positive + negative per policy (see supabase-schema-rls/references/rls-testing.md) | — | — | — |
| Background job | idempotency; retry classification | with real DB | — | — | — |

## Critical paths (always e2e)
Sign-up/sign-in, tenant switch, primary create flow, payment/plan change, export/download, permission-denied screen.

## Mock policy
| Mock | Allowed | Not allowed |
|---|---|---|
| `lib/db` functions in service unit tests | yes (`vi.mock('@/lib/db/invoices')`) | mocking the service under test |
| External HTTP (Stripe, email) | yes, with recorded fixtures; one contract test per payload | live calls in CI |
| Time | `vi.useFakeTimers()` / injected `now()` | `Date.now()` sprinkled in code |
| Supabase client in integration tests | no — real local stack | mocking RLS |
| Next.js `cookies()`/`headers()` | wrap in `server/auth.ts`, mock that | mocking `next/headers` everywhere |

## Fixtures
- `tests/fixtures/seed-ids.ts` — deterministic UUIDs matching `supabase/seed.sql`.
- `tests/fixtures/builders.ts` — `buildInvoice(overrides)` builders, never hand-written objects in tests.
- `tests/fixtures/payloads/<provider>/*.json` — recorded external payloads (secrets stripped).

## Coverage gate
- `server/` ≥ 80% lines and branches (`vitest --coverage`, `coverage-summary.json` checked in CI).
- `lib/db` measured by integration run.
- UI components: no numeric gate; critical flows by e2e.

## Naming
`describe('<unit>')` → `it('<does X> when <condition>')`. One behaviour per `it`. Arrange-Act-Assert with blank lines between.
