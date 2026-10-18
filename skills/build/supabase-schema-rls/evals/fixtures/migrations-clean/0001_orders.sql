-- fictional fixture: tenant-scoped orders table with RLS
-- rollback: drop policy "orders_tenant_select" on public.orders; drop table public.orders;
create table public.orders (
  id bigint generated always as identity primary key,
  tenant_id uuid not null,
  owner_id uuid not null,
  total_cents integer not null default 0,
  created_at timestamptz not null default now()
);
create index orders_tenant_id_idx on public.orders (tenant_id);
alter table public.orders enable row level security;
create policy "orders_tenant_select" on public.orders for select to authenticated
  using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
