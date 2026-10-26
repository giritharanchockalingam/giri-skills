# RLS Policy Patterns (Supabase / Postgres)

Convention: JWT carries `tenant_id` and `role` in `app_metadata` (set server-side via Auth hook or admin API; users cannot edit `app_metadata`). Helper functions below read them once per statement.

## 0. Helpers (create once, `0001_init.sql`)
```sql
create schema if not exists app;

create or replace function app.tenant_id() returns uuid
language sql stable as $$
  select nullif(((select auth.jwt()) -> 'app_metadata' ->> 'tenant_id'), '')::uuid
$$;

create or replace function app.role() returns text
language sql stable as $$
  select coalesce((select auth.jwt()) -> 'app_metadata' ->> 'role', 'member')
$$;

create or replace function app.has_role(required text) returns boolean
language sql stable as $$
  -- ordinal hierarchy: owner > admin > member > viewer
  select array_position(array['viewer','member','admin','owner'], app.role())
      >= array_position(array['viewer','member','admin','owner'], required)
$$;
```
Why `(select auth.jwt())`: the planner evaluates it once per statement instead of per row (initPlan). Measurable on large tables.

## 1. Tenant isolation (default for every tenant-scoped table)
```sql
alter table public.invoices enable row level security;

create policy invoices_select_tenant on public.invoices
  for select to authenticated
  using (tenant_id = (select app.tenant_id()));

create policy invoices_insert_tenant on public.invoices
  for insert to authenticated
  with check (tenant_id = (select app.tenant_id()));

create policy invoices_update_tenant on public.invoices
  for update to authenticated
  using (tenant_id = (select app.tenant_id()))
  with check (tenant_id = (select app.tenant_id()));

create policy invoices_delete_admin on public.invoices
  for delete to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));
```
Rules: `tenant_id uuid not null references public.tenants(id)`; index `(tenant_id, <sort col>)`; never let the client supply `tenant_id` — set it from the JWT in a `before insert` trigger or default: `default app.tenant_id()`.

## 2. Owner (row belongs to a user)
```sql
create policy notes_owner_all on public.notes
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
```
Combine with tenant when both apply: `tenant_id = (select app.tenant_id()) and user_id = (select auth.uid())`. Owner-only tables still carry `tenant_id` for reporting and deletion cascades.

## 3. Role-based (within tenant)
| Operation | viewer | member | admin | owner |
|---|---|---|---|---|
| select | ✓ | ✓ | ✓ | ✓ |
| insert | | ✓ | ✓ | ✓ |
| update | | own rows | ✓ | ✓ |
| delete | | | ✓ | ✓ |
| manage members / billing | | | ✓ | ✓ |
| delete tenant | | | | ✓ |

```sql
create policy projects_update_member_own_or_admin on public.projects
  for update to authenticated
  using (
    tenant_id = (select app.tenant_id())
    and ( created_by = (select auth.uid()) or (select app.has_role('admin')) )
  )
  with check (
    tenant_id = (select app.tenant_id())
    and ( created_by = (select auth.uid()) or (select app.has_role('admin')) )
  );
```
Prefer one policy per (operation, role tier). Postgres ORs multiple permissive policies for the same operation — convenient, but a stray broad policy silently widens access. Audit with `select * from pg_policies where tablename = 'x'`.

## 4. Public read (marketing content, published docs)
```sql
alter table public.articles enable row level security;

create policy articles_public_read on public.articles
  for select to anon, authenticated
  using (status = 'published');

create policy articles_write_admin on public.articles
  for all to authenticated
  using ((select app.has_role('admin'))) with check ((select app.has_role('admin')));
```
Rules: predicate on a status column, never `using (true)` on a table that also holds drafts; expose through a view with only public columns if the table has internal fields.

## 5. Service-role / admin paths
- Service role bypasses RLS. Allowed only in `server/services/**` or `supabase/functions/**`, through `lib/supabase/admin.ts`, with the reason in a comment.
- Prefer `security definer` functions with explicit checks over service-role clients for cross-tenant admin reads:
```sql
create or replace function app.admin_tenant_summary(p_tenant uuid)
returns table (tenant_id uuid, users bigint)
language sql security definer set search_path = '' as $$
  select t.id, count(u.id) from public.tenants t
  left join public.tenant_members u on u.tenant_id = t.id
  where t.id = p_tenant and (select app.has_role('owner'))
  group by t.id
$$;
revoke all on function app.admin_tenant_summary(uuid) from public, anon;
grant execute on function app.admin_tenant_summary(uuid) to authenticated;
```

## 6. Common bypass mistakes
| # | Mistake | Effect | Fix |
|---|---|---|---|
| 1 | Table created without `enable row level security` | anon key reads everything | linter flags; enable in the same migration |
| 2 | RLS enabled, zero policies, app "works" because it uses service role | client dirs leak service role | move to server; add real policies |
| 3 | `using` only on update/insert | user can move a row into another tenant | always add `with check` |
| 4 | `tenant_id` taken from request body | attacker posts another tenant's id | default/trigger from JWT; policy `with check` |
| 5 | Claims read from `user_metadata` | user can edit `user_metadata` → privilege escalation | only `app_metadata` |
| 6 | `security definer` without `set search_path = ''` | search-path hijack | always pin |
| 7 | View over RLS table owned by postgres (`security_invoker` off) | view bypasses RLS | `create view … with (security_invoker = true)` |
| 8 | Policy `to public` instead of `to authenticated` | anon role matches | name roles explicitly |
| 9 | Storage bucket public or policy missing | files readable by URL | bucket private; policy on `storage.objects` keyed by `(storage.foldername(name))[1] = tenant_id` |
| 10 | Realtime/`postgres_changes` on table without policies | change feed leaks rows | RLS applies to Realtime only if policies exist |
| 11 | `auth.uid()` in policy on a table written by webhooks (no JWT) | inserts fail or get forced through service role | dedicated `security definer` ingest function |
| 12 | Function `grant execute … to public` default | anon can call RPC | revoke from public/anon explicitly |
| 13 | Join to a non-RLS lookup table that embeds tenant data | leak through the join | RLS on every table, even "reference" tables |
| 14 | Cross-tenant unique constraint (`unique(email)`) | tenant A can probe B's emails via conflict errors | `unique(tenant_id, email)` |

## 7. Performance checklist
- Index every column used in a policy predicate (`tenant_id`, `user_id`, `status`).
- Wrap `auth.uid()`, `auth.jwt()`, helper calls in `(select …)`.
- Avoid `exists (select … from memberships …)` per row when a JWT claim can carry the answer; refresh claims on role change.
- `explain analyze` the hot query as the `authenticated` role (`set role authenticated; set request.jwt.claims = '…'`).
