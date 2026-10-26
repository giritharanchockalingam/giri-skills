# Conventions Checklist (used in the verify gate)

Report as: rule → pass / fail / n.a. → file:line. Fix every fail before returning.

| ID | Rule | How to check |
|---|---|---|
| L1 | No Supabase client call outside `lib/db` / `server/services` / `lib/supabase` | `grep -rn "from('" app components server/actions` → empty |
| L2 | `server-only` imported in `lib/db/*`, `server/**`, `lib/supabase/server.ts`, `admin.ts` | grep |
| L3 | Service-role client only in `lib/supabase/admin.ts`, imported only by `server/services` | `rls_lint.py --client-dirs` |
| C1 | `"use client"` files have a reason comment and no server-only imports | read each |
| C2 | Client components receive serializable props only | typecheck + read |
| C3 | Forms use `useActionState` + server action; work without JS | read |
| A1 | Every action/route: zod parse → `requireUser/Role` → service → map result | read each action |
| A2 | Tenant/user ids never taken from client input | read |
| A3 | Mutations `revalidateTag` scoped by tenant | grep `revalidate` |
| E1 | Services return `Result`; no `throw` for expected failures | grep `throw` in `server/services` |
| E2 | PG errors mapped via `lib/db/errors.ts`; no raw messages to client | read |
| E3 | `NOT_FOUND` vs `AUTH_FORBIDDEN` indistinguishable on reads | read |
| G1 | `lib/logger` only; `no-console` lint passes | `npm run lint` |
| G2 | Request-scoped child logger with `requestId`, `tenantId` | read |
| G3 | No PII/body/tokens in log context | read |
| N1 | File/function/error-code naming per `layering.md` | read |
| N2 | New env var in `.env.example` and `lib/env.ts` | diff |
| T1 | Unit tests for validators + services; e2e for new page path | test run |
| T2 | lint + typecheck + full unit suite + build green | commands |
| P1 | No `useEffect` data fetching; no waterfalls (`Promise.all`) | read |
| P2 | Dynamic import for heavy client deps; `next/image`, `next/font` | read |
| S1 | `params`/`searchParams` awaited and zod-validated | read |
| S2 | Webhook route verifies signature before parsing | read |
