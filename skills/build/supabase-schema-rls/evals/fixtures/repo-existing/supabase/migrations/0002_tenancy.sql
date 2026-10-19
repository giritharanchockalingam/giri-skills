-- 0002_tenancy.sql (fictional eval fixture) — applied: tenancy retrofitted, the open policy replaced.
-- rollback: drop policy projects_select_tenant on public.projects; drop policy projects_insert_member on public.projects; alter table public.projects drop column tenant_id; drop table public.scratch_imports;
alter table public.projects add column tenant_id uuid not null;
create index projects_tenant_idx on public.projects (tenant_id);
drop policy if exists projects_all on public.projects;
create policy projects_select_tenant on public.projects for select to authenticated
  using (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);
create policy projects_insert_member on public.projects for insert to authenticated
  with check (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);
create table public.scratch_imports (
  id uuid primary key,
  payload jsonb
);
