# Security Review Method — reasoning, not checklist (fallback for sentry:security-review)

A checklist finds what it lists. A threat model finds what the change actually enables. Do the model first; use the category table only to make sure nothing was skipped.

## Step 1 — Inventory the change by surface
| Surface | Trusts | Typical sinks |
|---|---|---|
| Server action | session cookie; nothing in `formData` | DB write, revalidate, redirect, email |
| Route handler | nothing (public) unless signature/API key verified | DB, queue, external call |
| Middleware | cookie only | redirect, header set |
| RSC page / layout | session; `params`/`searchParams` are untrusted | DB read, render |
| Client component | nothing; it runs on attacker's machine | action call, fetch |
| Migration / policy | — | data exposure across tenants |
| Edge function / job | service role — highest privilege | everything |
| Env / CI | repo contributors | secret exposure |

## Step 2 — Six questions per change
| # | Question | What a weak answer looks like |
|---|---|---|
| 1 | Who can reach this? (anon, any user, tenant member, admin, internal only) | "The UI hides the button" |
| 2 | What do they control? (body, params, headers, files, timing, order) | "The id comes from our own page" |
| 3 | What does it touch? (tables, buckets, external systems, other tenants' rows) | "Just reads" (reads leak) |
| 4 | Worst realistic outcome? (cross-tenant read, privilege escalation, data loss, RCE, DoS, money) | "Nothing sensitive" (ids, emails, counts are sensitive) |
| 5 | Which control stops it, and where is it in this diff? | "RLS will catch it" (is RLS enabled on that table? does the service-role path bypass it?) |
| 6 | How would we know it happened? (log, audit, alert) | "We'd notice" |

Write the answers for each change in the report. Findings come from questions 4–5 having a gap.

## Step 3 — Trace discipline
For every candidate finding:
1. Entry: file:line where untrusted data enters.
2. Each transformation: file:line (parse? validate? authorize?).
3. Sink: file:line where it hits DB/FS/network/response.
4. Control gap: the hop where the needed check is missing or bypassable.
5. Exploit sketch: one concrete request that demonstrates it.

If step 5 cannot be written, downgrade to "question for the author".

## Step 4 — Category sweep (after the model, to catch omissions)
| Category | Key questions | Stack hot spots |
|---|---|---|
| Authorization (authz) | Is the role check on the server? Is it per request? Does it check tenant AND role? | server actions without `requireRole`; RSC pages relying on layout checks; API routes |
| IDOR | Is the id scoped to the tenant/user at the DB (RLS) and in the query? | `.eq('id', id)` without tenant filter on a non-RLS table; service-role queries |
| Mass assignment | Is the whole `formData`/body spread into an insert/update? | `update(parsed)` where schema allows `tenant_id`, `role`, `status` |
| Injection | SQL (raw `rpc` with string concat), command, template, header, log injection | `.rpc()` with interpolated SQL; `sql` template misuse; `JSON.parse` of untrusted |
| RLS bypass | Service role in reachable code? Policies missing `with check`? `security definer` without checks? Views without `security_invoker`? | `lib/supabase/admin.ts` imports; migrations |
| Secrets | `NEXT_PUBLIC_` on a secret; secret in logs; `.env` committed; secret in client bundle via import | `lib/env.ts` split; `next.config` env; logger context |
| SSRF | User-controlled URL fetched server-side (webhooks, image proxies, import-by-URL) | route handlers; `fetch(url)` with url from body |
| Open redirect | `redirect(searchParams.next)` unvalidated | sign-in flows |
| File upload | Type/size validated? Path from user? Bucket public? Served with correct content-type? | Storage policies; `storage.from().upload(userPath)` |
| CSRF | Server actions are POST with origin checks by Next; custom route handlers accepting cookies need CSRF token or same-site checks | `app/api/**` with cookie auth |
| Rate limiting / DoS | Public actions (sign-up, password reset, contact) limited? Expensive queries bounded (`limit`)? | route handlers; search endpoints |
| Crypto / tokens | Tokens random (`crypto.randomUUID`/`randomBytes`), hashed at rest, expiring, single-use? | invite links, API keys |
| Logging / privacy | PII or secrets in logs? Audit for sensitive actions? | logger context; audit trigger coverage |
| Dependency / supply chain | New deps? Postinstall scripts? Lockfile changed unexpectedly? | `package.json` diff |
| Error handling | Stack traces or PG messages to client? Different responses for exists/not-exists? | `toResponse`; `NOT_FOUND` vs `FORBIDDEN` |
| Next.js specifics | See `stack-specifics.md` | server-action exposure, `params` trust, middleware bypass |

## Step 5 — Write the finding
```
[HIGH] Cross-tenant invoice read via export endpoint
Trace: app/api/export/route.ts:14 (searchParams.tenantId) → server/services/export.ts:22 (passes tenantId) → lib/supabase/admin.ts (service role) → invoices
Gap: tenantId taken from query, service-role client bypasses RLS; no comparison to session tenant.
Exploit: GET /api/export?tenantId=<other> with any valid session.
Fix: drop tenantId param; use session.tenantId; use cookie client so RLS applies; add negative test.
```

## Anti-patterns in reviews
- Reporting "consider adding rate limiting" without identifying the endpoint and the abuse.
- Rating by category ("injection = critical") instead of reachability × impact.
- Listing 30 Low/Info items that hide the 2 Highs. Lead with the worst.
- Fixing by adding a client-side check.
