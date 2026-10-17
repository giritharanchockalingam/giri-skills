-- rls-policies.sql — copy-paste snippets. Replace <table>, <col>. All assume app.* helpers from 0001_init.

-- ===== Helpers (once) =====
create schema if not exists app;
create or replace function app.tenant_id() returns uuid language sql stable as $$
  select nullif(((select auth.jwt()) -> 'app_metadata' ->> 'tenant_id'), '')::uuid $$;
create or replace function app.role() returns text language sql stable as $$
  select coalesce((select auth.jwt()) -> 'app_metadata' ->> 'role', 'member') $$;
create or replace function app.has_role(required text) returns boolean language sql stable as $$
  select array_position(array['viewer','member','admin','owner'], app.role())
      >= array_position(array['viewer','member','admin','owner'], required) $$;
create or replace function app.set_updated_at() returns trigger language plpgsql as $$
  begin new.updated_at = now(); return new; end $$;

-- ===== Pattern 1: tenant isolation =====
alter table public.<table> enable row level security;
create policy <table>_select_tenant on public.<table> for select to authenticated
  using (tenant_id = (select app.tenant_id()));
create policy <table>_insert_tenant on public.<table> for insert to authenticated
  with check (tenant_id = (select app.tenant_id()));
create policy <table>_update_tenant on public.<table> for update to authenticated
  using (tenant_id = (select app.tenant_id())) with check (tenant_id = (select app.tenant_id()));
create policy <table>_delete_tenant_admin on public.<table> for delete to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));

-- ===== Pattern 2: owner =====
create policy <table>_owner_all on public.<table> for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- ===== Pattern 2b: tenant + owner =====
create policy <table>_tenant_owner_write on public.<table> for update to authenticated
  using (tenant_id = (select app.tenant_id()) and created_by = (select auth.uid()))
  with check (tenant_id = (select app.tenant_id()) and created_by = (select auth.uid()));

-- ===== Pattern 3: role-based (own rows OR admin) =====
create policy <table>_update_own_or_admin on public.<table> for update to authenticated
  using (tenant_id = (select app.tenant_id()) and (created_by = (select auth.uid()) or (select app.has_role('admin'))))
  with check (tenant_id = (select app.tenant_id()) and (created_by = (select auth.uid()) or (select app.has_role('admin'))));

-- ===== Pattern 4: public read of published rows =====
create policy <table>_public_read on public.<table> for select to anon, authenticated
  using (status = 'published');
create policy <table>_admin_write on public.<table> for all to authenticated
  using ((select app.has_role('admin'))) with check ((select app.has_role('admin')));

-- ===== Pattern 5: storage bucket scoped by tenant folder =====
-- bucket 'tenant-files' private; object path '<tenant_id>/<file>'
create policy tenant_files_select on storage.objects for select to authenticated
  using (bucket_id = 'tenant-files' and (storage.foldername(name))[1] = (select app.tenant_id())::text);
create policy tenant_files_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'tenant-files' and (storage.foldername(name))[1] = (select app.tenant_id())::text);

-- ===== Pattern 6: secure view over RLS table =====
create view public.<table>_public with (security_invoker = true) as
  select id, title, published_at from public.<table> where status = 'published';

-- ===== Pattern 7: security definer RPC with pinned search_path =====
create or replace function app.<fn>(p_arg uuid) returns setof public.<table>
language sql security definer set search_path = '' as $$
  select * from public.<table> where tenant_id = (select app.tenant_id()) and id = p_arg
$$;
revoke all on function app.<fn>(uuid) from public, anon;
grant execute on function app.<fn>(uuid) to authenticated;

-- ===== Audit of policies on a table =====
-- select policyname, cmd, roles, qual, with_check from pg_policies where tablename = '<table>';
