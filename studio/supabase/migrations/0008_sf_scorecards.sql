-- 0008_sf_scorecards.sql — scorecards: each catalog entity scored by library skills on its real files.
-- Append-only history (one row per check run); the latest per (entity, check) is the scorecard. sf_ prefix; idempotent.
-- rollback: (manual — drops the scorecard history; the catalog is unaffected)
--   drop view if exists public.sf_scorecard_latest;
--   drop table if exists public.sf_scorecard_results cascade;

create table if not exists public.sf_scorecard_results (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  entity_id     uuid not null references public.sf_catalog_entities(id) on delete cascade,
  check_id      text not null check (check_id ~ '^[a-z][a-z0-9-]{0,40}$'),
  skill         text not null check (skill ~ '^[a-z0-9-]+/[a-z0-9-]+$'),
  verdict       text not null check (verdict in ('pass', 'warn', 'fail', 'error', 'skipped')),
  summary       text not null default '',
  findings      int,
  commit_sha    text check (commit_sha is null or commit_sha ~ '^[0-9a-f]{40}$'),
  details       jsonb not null default '{}'::jsonb,       -- report excerpt, output hashes, files used, partial, runtime status
  duration_ms   int,
  run_by        uuid not null references auth.users(id),
  created_at    timestamptz not null default now()
);
create index if not exists sf_scorecard_results_entity_idx on public.sf_scorecard_results(workspace_id, entity_id, check_id, created_at desc);

alter table public.sf_scorecard_results enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_scorecard_results' and policyname='sf_scorecard_select') then execute $p$
    create policy sf_scorecard_select on public.sf_scorecard_results for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_scorecard_results' and policyname='sf_scorecard_insert') then execute $p$
    create policy sf_scorecard_insert on public.sf_scorecard_results for insert to authenticated
    with check (public.sf_has_role(workspace_id, array['author', 'admin']) and run_by = auth.uid()
                and exists (select 1 from public.sf_catalog_entities e where e.id = entity_id and e.workspace_id = sf_scorecard_results.workspace_id)) $p$; end if;
end $$;
-- history is evidence: no update or delete policy (rows go only when their entity or workspace is deleted)
grant select, insert on public.sf_scorecard_results to authenticated;

create or replace view public.sf_scorecard_latest with (security_invoker = true) as
  select distinct on (entity_id, check_id) *
  from public.sf_scorecard_results
  order by entity_id, check_id, created_at desc;
grant select on public.sf_scorecard_latest to authenticated;
