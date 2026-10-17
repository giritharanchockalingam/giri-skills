# Stack Conventions

Default stack: TypeScript · Next.js (App Router) · React · Supabase (Postgres, Auth, RLS, Storage, Edge Functions) · Vercel · GitHub Actions · Python 3.12 for scripts/agents · GCP when cloud services beyond Vercel/Supabase are required.

## Repo layout (Next.js app)
```
app/            routes (App Router); server components by default
components/     ui/ (primitives), features/<domain>/
lib/            supabase/ (server + browser clients), db/ (queries), utils/
server/         actions/ (server actions), services/ (domain logic), validators/ (zod)
supabase/       migrations/, seed.sql, functions/
tests/          unit/ (vitest), e2e/ (playwright), fixtures/
docs/           SPEC.md, HANDOFF.md, adr/NNNN-title.md
.github/workflows/
```

## Rules
| Area | Convention |
|---|---|
| Data access | Only through `lib/db` or `server/services`. No Supabase calls in components. |
| Auth | Supabase Auth; RLS on every table; service-role key only in server-side code, never shipped to client. |
| Validation | zod schemas in `server/validators`; validate at the boundary (server action / route handler). |
| Errors | Typed `Result<T, E>` from services; never throw across the server/client boundary; log with correlation id. |
| Logging | Structured JSON (`level`, `msg`, `requestId`, `userId?`, `tenantId?`). No `console.log` in committed code. |
| Env | `.env.example` is the contract; every var documented; `env.ts` parses with zod at boot. |
| Migrations | One migration per change, forward-only, with a `-- rollback:` comment block. Never edit an applied migration. |
| Tests | Unit for services/validators; integration for db queries against local Supabase; e2e for critical paths. Coverage gate ≥ 80% on `server/`. |
| CI | lint → typecheck → unit → build → e2e (preview) → deploy. Prod deploy only from `main` via tag. |
| Multi-tenant | `tenant_id` on every tenant-scoped table; RLS policy `tenant_id = auth.jwt()->>'tenant_id'`; composite indexes lead with `tenant_id`. |
| Secrets | Vercel/Supabase env only. Never in repo, never in logs. |
| Python | `uv` or `pip` with pinned `requirements.txt`; `ruff` + `pytest`; type hints required. |
