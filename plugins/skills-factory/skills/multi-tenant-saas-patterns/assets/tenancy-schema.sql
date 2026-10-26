-- tenancy-schema.sql — reference DDL for core multi-tenant tables. Hand to supabase-schema-rls to turn into
-- migrations with rollback blocks. Assumes app.* helpers (see supabase-schema-rls/assets/rls-policies.sql).

create table public.tenants (
  id          uuid primary key default gen_random_uuid(),
  slug        text not null unique check (slug ~ '^[a-z0-9]([a-z0-9-]{1,38}[a-z0-9])?$'),
  name        text not null,
  plan_id     text not null default 'free',
  status      text not null default 'active' check (status in ('active','suspended','deleting')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table public.tenant_members (
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  role        text not null check (role in ('viewer','member','admin','owner')),
  status      text not null default 'active' check (status in ('active','removed')),
  invited_by  uuid references auth.users(id),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  primary key (tenant_id, user_id)
);
create index tenant_members_user_idx on public.tenant_members (user_id);

create table public.invitations (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  email       text not null,
  role        text not null check (role in ('viewer','member','admin')),
  token_hash  text not null unique,
  expires_at  timestamptz not null default now() + interval '7 days',
  accepted_at timestamptz,
  invited_by  uuid not null references auth.users(id),
  created_at  timestamptz not null default now(),
  unique (tenant_id, email)
);

create table public.profiles (
  user_id           uuid primary key references auth.users(id) on delete cascade,
  display_name      text,
  default_tenant_id uuid references public.tenants(id) on delete set null,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

-- Membership-aware helper: active member of the JWT tenant (guards stale claims after removal)
create or replace function app.is_active_member() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.tenant_members m
    where m.tenant_id = (select app.tenant_id()) and m.user_id = (select auth.uid()) and m.status = 'active'
  ) $$;

-- RLS
alter table public.tenants enable row level security;
create policy tenants_select_member on public.tenants for select to authenticated
  using (id = (select app.tenant_id()) and (select app.is_active_member()));
create policy tenants_update_admin on public.tenants for update to authenticated
  using (id = (select app.tenant_id()) and (select app.has_role('admin')))
  with check (id = (select app.tenant_id()) and (select app.has_role('admin')));
create policy tenants_delete_owner on public.tenants for delete to authenticated
  using (id = (select app.tenant_id()) and (select app.has_role('owner')));

alter table public.tenant_members enable row level security;
create policy members_select_tenant on public.tenant_members for select to authenticated
  using (tenant_id = (select app.tenant_id()) or user_id = (select auth.uid()));
create policy members_update_admin on public.tenant_members for update to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')))
  with check (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));
create policy members_delete_admin on public.tenant_members for delete to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));
-- inserts happen via security definer functions (accept_invite, create_personal_tenant), not direct.

alter table public.invitations enable row level security;
create policy invitations_select_admin on public.invitations for select to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));
create policy invitations_insert_admin on public.invitations for insert to authenticated
  with check (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')) and invited_by = (select auth.uid()));
create policy invitations_delete_admin on public.invitations for delete to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));

alter table public.profiles enable row level security;
create policy profiles_owner_all on public.profiles for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- Last-owner guard
create or replace function app.guard_last_owner() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if (tg_op = 'DELETE' or new.role <> 'owner' or new.status <> 'active') and old.role = 'owner' and old.status = 'active' then
    if (select count(*) from public.tenant_members where tenant_id = old.tenant_id and role = 'owner' and status = 'active' and user_id <> old.user_id) = 0 then
      raise exception 'tenant must keep at least one owner' using errcode = '23514';
    end if;
  end if;
  return coalesce(new, old);
end $$;
create trigger tenant_members_last_owner before update or delete on public.tenant_members
  for each row execute function app.guard_last_owner();

-- rollback: drop in reverse order (trigger, function, policies, tables profiles → invitations → tenant_members → tenants, function is_active_member)
