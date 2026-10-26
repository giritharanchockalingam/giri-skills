# Recurring Bug Causes in Next.js + Supabase + Vercel Apps

| Symptom | Usual cause | Where to look | Fix shape |
|---|---|---|---|
| Works locally, 500 on Vercel | missing env var; `lib/env.ts` parse fails | Vercel env per environment; build logs | add var; keep `.env.example` in sync |
| Empty list for a user who should see rows | RLS policy predicate wrong, claim missing from JWT (`app_metadata`), or stale session after role change | policy; `auth.jwt()` output; refresh token | fix policy + integration negative/positive test; force refresh after role change |
| `42501 new row violates row-level security` | insert lacks `tenant_id` or `with check` mismatch | migration; action building the row | default `tenant_id` from JWT; fix `with check` |
| Data from another tenant visible | service-role client used in a user path; non-RLS table; `security definer` view | `lib/supabase/admin.ts` imports; `rls_lint.py` | cookie client; enable RLS; `security_invoker` view |
| Action "does nothing" | `redirect()` inside try/catch; unawaited promise; `revalidateTag` wrong tag | action body | move redirect out; await; scope tag |
| Stale data after mutation | fetch cached (`"use cache"` / `revalidate`) and tag not invalidated | fetch options; mutation | `revalidateTag` with tenant-scoped tag |
| `params` undefined / Promise | Next 15 async `params` not awaited | page/route | `const { id } = await params` |
| Hydration mismatch | time/random/locale rendered on server differently from client; `Date` across boundary | component | compute on one side; pass ISO strings |
| "Server functions cannot be called in client" | server-only import in client component | import graph | move to action; `server-only` marker |
| Slow page | fetch waterfall (sequential awaits); per-row `auth.uid()` in policy; missing index | RSC; `explain analyze` | `Promise.all`; `(select auth.uid())`; index leading `tenant_id` |
| Migration fails in prod but not staging | data violates new constraint; edited applied migration | prod data; checksums | expand/contract; new migration |
| Intermittent e2e failure | shared test data; non-web-first waits | spec | unique data per worker; `expect(locator)` |
| Edge function 401 | hook/webhook secret mismatch | function env | align secrets; verify signature |
| Cron route runs for anyone | missing `CRON_SECRET` check | route | bearer check |
| User sees another user's cached page | `Cache-Control` public on personalised route; `force-static` | route segment config | `dynamic = 'force-dynamic'`; no-store |
