-- 0017_sf_blueprints.sql — the catalog models more than repositories: services (Vercel projects) and databases
-- (Supabase projects), with typed relations between entities (service built_from repository, service uses_database
-- database). Every relation records where it was learned (evidence). Syncs are logged per provider.
-- sf_ prefix only; idempotent.
-- rollback: (manual — drops relations and non-repository entities; repositories are untouched)
--   drop table if exists public.sf_catalog_relations cascade;
--   drop function if exists public.sf_relation_same_workspace();
--   delete from public.sf_catalog_entities where kind <> 'repository';
--   alter table if exists public.sf_catalog_syncs drop column if exists provider;

alter table public.sf_catalog_entities drop constraint if exists sf_catalog_entities_kind_check;
alter table public.sf_catalog_entities add constraint sf_catalog_entities_kind_check check (kind in ('repository', 'service', 'database'));
alter table public.sf_catalog_entities drop constraint if exists sf_catalog_entities_source_check;
alter table public.sf_catalog_entities add constraint sf_catalog_entities_source_check check (source in ('github', 'vercel', 'supabase'));
alter table public.sf_catalog_syncs add column if not exists provider text not null default 'github' check (provider in ('github', 'vercel', 'supabase'));

create table if not exists public.sf_catalog_relations (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  from_id       uuid not null references public.sf_catalog_entities(id) on delete cascade,
  to_id         uuid not null references public.sf_catalog_entities(id) on delete cascade,
  type          text not null check (type in ('built_from', 'uses_database')),
  evidence      text not null default '' check (length(evidence) <= 500),
  source        text not null check (source in ('github', 'vercel', 'supabase')),
  created_at    timestamptz not null default now(),
  unique (from_id, to_id, type),
  check (from_id <> to_id)
);
create index if not exists sf_catalog_relations_ws_idx on public.sf_catalog_relations (workspace_id, type);
create index if not exists sf_catalog_relations_to_idx on public.sf_catalog_relations (to_id);

-- both ends must be in the relation's workspace (a relation can never point across workspaces)
create or replace function public.sf_relation_same_workspace() returns trigger language plpgsql set search_path = public as $$
begin
  if not exists (select 1 from public.sf_catalog_entities where id = new.from_id and workspace_id = new.workspace_id)
     or not exists (select 1 from public.sf_catalog_entities where id = new.to_id and workspace_id = new.workspace_id) then
    raise exception 'relation ends must belong to the relation''s workspace' using errcode = 'check_violation';
  end if;
  return new;
end $$;
do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_catalog_relations_ws') then
    create trigger sf_catalog_relations_ws before insert or update on public.sf_catalog_relations for each row execute function public.sf_relation_same_workspace(); end if;
end $$;

alter table public.sf_catalog_relations enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_catalog_relations' and policyname='sf_relations_select') then execute $p$
    create policy sf_relations_select on public.sf_catalog_relations for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_catalog_relations' and policyname='sf_relations_write') then execute $p$
    create policy sf_relations_write on public.sf_catalog_relations for all to authenticated
    using (public.sf_has_role(workspace_id, array['author', 'admin'])) with check (public.sf_has_role(workspace_id, array['author', 'admin'])) $p$; end if;
end $$;
grant select, insert, update, delete on public.sf_catalog_relations to authenticated;
