-- 0002_tenancy.sql (fictional eval fixture: tenancy retrofitted onto the existing projects table)
create table public.tenants (
  id   uuid primary key default gen_random_uuid(),
  name text not null
);
alter table public.tenants enable row level security;
create policy tenants_select_member on public.tenants for select to authenticated
  using (id = (select (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))::uuid);

alter table public.projects add column tenant_id uuid not null references public.tenants(id);
create index projects_tenant_created_idx on public.projects (tenant_id, created_at desc);
create policy projects_select_tenant on public.projects for select to authenticated
  using (tenant_id = (select (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))::uuid);

create table public.tenant_members (
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  user_id   uuid not null references auth.users(id),
  role      text not null check (role in ('viewer','member','admin','owner'))
);
alter table public.tenant_members add constraint tenant_members_pk primary key (tenant_id, user_id);
alter table public.tenant_members enable row level security;
create policy members_select_tenant on public.tenant_members for select to authenticated
  using (tenant_id = (select (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))::uuid);
-- rollback:
-- drop table public.tenant_members; alter table public.projects drop column tenant_id; drop table public.tenants;
