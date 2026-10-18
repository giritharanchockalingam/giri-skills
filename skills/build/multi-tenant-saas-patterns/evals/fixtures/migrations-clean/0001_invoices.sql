-- 0001_invoices.sql (eval fixture)
create table public.invoices (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  number     text not null,
  amount     bigint not null,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  unique (tenant_id, number)
);
create index invoices_tenant_created_idx on public.invoices (tenant_id, created_at desc);
alter table public.invoices enable row level security;
create policy invoices_select_tenant on public.invoices for select to authenticated
  using (tenant_id = (select app.tenant_id()));
create policy invoices_insert_member on public.invoices for insert to authenticated
  with check (tenant_id = (select app.tenant_id()) and (select app.has_role('member')));

create table public.plans (
  id    text primary key,
  name  text not null
);
alter table public.plans enable row level security;
create policy plans_select_all on public.plans for select to authenticated using (true);
-- rollback:
-- drop table public.invoices; drop table public.plans;
