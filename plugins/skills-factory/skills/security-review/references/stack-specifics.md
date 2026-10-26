# Stack-Specific Pitfalls — Next.js App Router · Supabase · Vercel

## Next.js server actions
| Pitfall | Why it matters | Check |
|---|---|---|
| Every exported function in a `"use server"` file is a public POST endpoint | "helper" functions become callable by anyone with the action id | only actions exported; helpers in non-`use server` modules |
| Closure-captured values are serialized to the client (encrypted, but present) | leaking server data; stale authz decisions captured at render | no secrets/ids in closures; re-check authz inside the action |
| `formData` ids trusted | IDOR / tenant hop | ids re-validated; tenant/user from session |
| Authz done in the layout/page, not the action | action callable directly without UI | `requireRole` inside every action |
| `redirect()` inside `try/catch` | swallowed `NEXT_REDIRECT` | redirect after try block |
| Returning full DB rows / `cause` | leaks internal fields, stack | `toActionState` strips; DTO mapping |
| Action does heavy work synchronously | DoS surface | enqueue; limit |
| `allowedOrigins` / `serverActions.bodySizeLimit` unset for multi-domain | CSRF-like cross-origin calls; large bodies | set in `next.config` when using custom domains/proxies |

## Next.js routing / RSC
| Pitfall | Check |
|---|---|
| `params`/`searchParams` used unvalidated in queries | zod parse; uuid check |
| Middleware as the only auth gate — can be bypassed by direct RSC/`_next/data` fetches or misconfigured matcher | per-page `requireUser()` too |
| `error.tsx` exposing `error.message` from server | show `requestId` + generic text in prod |
| Route handler with `export const dynamic = 'force-static'` caching user data | explicit `dynamic`/`revalidate` per route |
| `NEXT_PUBLIC_*` used for anything secret; `process.env.X` referenced in client component (inlined at build) | grep client files for `process.env` |
| `next.config.images.remotePatterns: '**'` | SSRF-ish image proxy; restrict hosts |
| `rewrites`/`proxy` to user-controlled destinations | allow-list |

## Supabase
| Pitfall | Check |
|---|---|
| Table without RLS reachable via anon key (PostgREST exposes every `public` table) | `rls_lint.py`; `select * from pg_tables where rowsecurity=false and schemaname='public'` |
| Policies without `with check` → row can be moved across tenants | lint RLS004 |
| Claims from `user_metadata` (user-editable via `auth.updateUser`) | only `app_metadata`, set server-side |
| Service-role key in client bundle / edge middleware / `NEXT_PUBLIC_` | lint RLS009; grep |
| `security definer` without `set search_path = ''` | lint RLS006 |
| Functions `grant execute to public` by default → anon can call RPC | explicit revoke |
| Storage bucket public or object path user-chosen | bucket private; path = `${tenantId}/${uuid}`; policies on `storage.objects` |
| Realtime channel on table lacking policies | RLS covers Realtime only via policies |
| `auth.users` email enumeration via sign-up/reset responses | uniform responses; rate limit |
| Supabase Auth hooks / Edge Functions use service role — input trusted | validate payload; verify hook secret |
| `.single()` errors leaking "0 rows" vs "forbidden" | map both to `NOT_FOUND` |
| Direct `SUPABASE_DB_URL` in app runtime | migrations/CI only |

## Vercel
| Pitfall | Check |
|---|---|
| Preview deployments unprotected with prod-like data | Vercel Authentication on previews; separate staging DB |
| Preview env vars pointing at prod Supabase | env matrix review |
| `VERCEL_AUTOMATION_BYPASS_SECRET` in client or logs | CI secret only |
| Cron routes (`vercel.json` crons) without auth | check `Authorization: Bearer ${CRON_SECRET}` |
| Log Drains to third party containing PII | logger redaction |
| Env var marked non-sensitive that is sensitive | mark "Sensitive" in Vercel so it cannot be read back |
| Build-time env inlined into client (`NEXT_PUBLIC_`) rotated without redeploy | rotation runbook includes redeploy |

## Python scripts / agents (when present)
- `subprocess` with `shell=True` and user input; `eval`; pickle from untrusted; `requests` without timeout; secrets in argv.
