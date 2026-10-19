-- 0015_sf_delivery.sql — delivery metrics (DORA-style) per catalog repository, as append-only snapshots computed from
-- GitHub (pull requests into the default branch; production deployments when the App may read them). History is the
-- trend. sf_ prefix only; idempotent.
-- Writers: authors and admins (the catalog sync and "Refresh" run as them); the server's webhook path (service role).
-- rollback: (manual — drops the snapshots only)
--   drop view if exists public.sf_delivery_latest;
--   drop table if exists public.sf_delivery_snapshots cascade;

create table if not exists public.sf_delivery_snapshots (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  entity_id     uuid not null references public.sf_catalog_entities(id) on delete cascade,
  metrics       jsonb not null,                 -- {"d30": Delivery, "d90": Delivery}
  notes         text[] not null default '{}',   -- what was measured instead of what, when the source was limited
  computed_by   uuid references auth.users(id),
  computed_at   timestamptz not null default now()
);
create index if not exists sf_delivery_snapshots_entity_idx on public.sf_delivery_snapshots (workspace_id, entity_id, computed_at desc);

alter table public.sf_delivery_snapshots enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_delivery_snapshots' and policyname='sf_delivery_select') then execute $p$
    create policy sf_delivery_select on public.sf_delivery_snapshots for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_delivery_snapshots' and policyname='sf_delivery_insert') then execute $p$
    create policy sf_delivery_insert on public.sf_delivery_snapshots for insert to authenticated
    with check (public.sf_has_role(workspace_id, array['author', 'admin']) and computed_by = auth.uid()
                and exists (select 1 from public.sf_catalog_entities e where e.id = entity_id and e.workspace_id = sf_delivery_snapshots.workspace_id)) $p$; end if;
end $$;
grant select, insert on public.sf_delivery_snapshots to authenticated;

create or replace view public.sf_delivery_latest with (security_invoker = true) as
  select distinct on (entity_id) * from public.sf_delivery_snapshots order by entity_id, computed_at desc;
grant select on public.sf_delivery_latest to authenticated;
