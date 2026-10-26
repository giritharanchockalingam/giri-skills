-- Migration: <YYYYMMDDHHMMSS>_<verb>_<object>
-- Purpose: <what and why; link SPEC § / plan file>
-- Depends on: <migration names>
-- Destructive: no | yes (expand/contract step N of 3)
-- Backfill: none | separate migration <name>

begin;

-- 1. Tables
create table public.<table> (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants(id) on delete cascade default app.tenant_id(),
  created_by  uuid not null references auth.users(id) default auth.uid(),
  -- columns
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- 2. Indexes (tenant_id leads every composite index)
create index <table>_tenant_created_idx on public.<table> (tenant_id, created_at desc);

-- 3. Triggers
create trigger <table>_set_updated_at before update on public.<table>
  for each row execute function app.set_updated_at();
create trigger <table>_audit after insert or update or delete on public.<table>
  for each row execute function app.audit_row();

-- 4. RLS (one policy per operation per role tier; using + with check on writes)
alter table public.<table> enable row level security;
create policy <table>_select_tenant on public.<table> for select to authenticated
  using (tenant_id = (select app.tenant_id()));
create policy <table>_insert_member on public.<table> for insert to authenticated
  with check (tenant_id = (select app.tenant_id()) and (select app.has_role('member')));
create policy <table>_update_admin on public.<table> for update to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')))
  with check (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));
create policy <table>_delete_admin on public.<table> for delete to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));

commit;

-- rollback:
-- begin;
-- drop trigger if exists <table>_audit on public.<table>;
-- drop trigger if exists <table>_set_updated_at on public.<table>;
-- drop policy if exists <table>_delete_admin on public.<table>;
-- drop policy if exists <table>_update_admin on public.<table>;
-- drop policy if exists <table>_insert_member on public.<table>;
-- drop policy if exists <table>_select_tenant on public.<table>;
-- drop index if exists <table>_tenant_created_idx;
-- drop table if exists public.<table>;
-- commit;
