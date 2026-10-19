-- 0011_sf_automations.sql — the workflow orchestrator: automations (when <GitHub event> in <repos> → run <checks>),
-- their runs, and the webhook deliveries they came from (deduplicated). Scorecard results gain a context so a pull
-- request's results never replace the default branch's scorecard. sf_ prefix only; idempotent.
-- Writers: admins manage automations (RLS); runs and deliveries are written only by the webhook processor on the
-- server (service role, no browser path) — members read them. A delivery is stored only for a linked installation.
-- rollback: (manual — drops automations and their history; scorecard results keep their rows)
--   drop table if exists public.sf_automation_runs cascade;
--   drop table if exists public.sf_automations cascade;
--   drop table if exists public.sf_github_deliveries cascade;

create table if not exists public.sf_automations (
  id                uuid primary key default gen_random_uuid(),
  workspace_id      uuid not null references public.sf_workspaces(id) on delete cascade,
  name              text not null check (length(name) between 1 and 120),
  trigger           text not null check (trigger in ('github.pull_request', 'github.push')),
  repos             text[] not null default '{}',          -- owner/name keys; empty = every catalog repository
  checks            text[] not null default '{}',          -- scorecard check ids; empty = every applicable check
  report_to_github  boolean not null default true,         -- post a Check Run on the commit / pull request
  enabled           boolean not null default true,
  created_by        uuid not null references auth.users(id),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create index if not exists sf_automations_ws_idx on public.sf_automations (workspace_id, trigger) where enabled;

create table if not exists public.sf_github_deliveries (
  delivery_id     text primary key check (length(delivery_id) between 1 and 100),   -- X-GitHub-Delivery: processed once
  workspace_id    uuid not null references public.sf_workspaces(id) on delete cascade, -- the installation's workspace
  event           text not null,
  installation_id bigint not null,
  received_at     timestamptz not null default now()
);
create index if not exists sf_github_deliveries_ws_idx on public.sf_github_deliveries (workspace_id, received_at desc);

create table if not exists public.sf_automation_runs (
  id              uuid primary key default gen_random_uuid(),
  workspace_id    uuid not null references public.sf_workspaces(id) on delete cascade,
  automation_id   uuid not null references public.sf_automations(id) on delete cascade,
  entity_id       uuid references public.sf_catalog_entities(id) on delete set null,
  repo            text not null,
  event           text not null,
  delivery_id     text,
  head_sha        text check (head_sha is null or head_sha ~ '^[0-9a-f]{40}$'),
  pr_number       int,
  status          text not null default 'running' check (status in ('running', 'succeeded', 'failed', 'skipped')),
  verdicts        jsonb not null default '{}'::jsonb,
  check_run_url   text check (check_run_url is null or check_run_url ~ '^https://'),
  error           text,
  started_at      timestamptz not null default now(),
  finished_at     timestamptz
);
create index if not exists sf_automation_runs_ws_idx on public.sf_automation_runs (workspace_id, started_at desc);

alter table public.sf_scorecard_results add column if not exists context text not null default 'default' check (context in ('default', 'pull_request'));
alter table public.sf_scorecard_results add column if not exists pr_number int;
alter table public.sf_scorecard_results add column if not exists automation_run_id uuid references public.sf_automation_runs(id) on delete set null;
-- the scorecard is the default branch's: pull-request results are evidence on the PR, not the repository's state
create or replace view public.sf_scorecard_latest with (security_invoker = true) as
  select distinct on (entity_id, check_id) *
  from public.sf_scorecard_results
  where context = 'default'
  order by entity_id, check_id, created_at desc;
grant select on public.sf_scorecard_latest to authenticated;

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_automations_updated_at') then
    create trigger sf_automations_updated_at before update on public.sf_automations for each row execute function public.sf_set_updated_at(); end if;
end $$;

alter table public.sf_automations       enable row level security;
alter table public.sf_automation_runs   enable row level security;
alter table public.sf_github_deliveries enable row level security;   -- written by the server only; members read their log
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_automations' and policyname='sf_automations_select') then execute $p$
    create policy sf_automations_select on public.sf_automations for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  -- any admin may create (as themselves), change or delete; the creator is recorded, not an owner lock
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_automations' and policyname='sf_automations_insert') then execute $p$
    create policy sf_automations_insert on public.sf_automations for insert to authenticated
    with check (public.sf_has_role(workspace_id, array['admin']) and created_by = auth.uid()) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_automations' and policyname='sf_automations_update') then execute $p$
    create policy sf_automations_update on public.sf_automations for update to authenticated
    using (public.sf_has_role(workspace_id, array['admin'])) with check (public.sf_has_role(workspace_id, array['admin'])) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_automations' and policyname='sf_automations_delete') then execute $p$
    create policy sf_automations_delete on public.sf_automations for delete to authenticated using (public.sf_has_role(workspace_id, array['admin'])) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_github_deliveries' and policyname='sf_github_deliveries_select') then execute $p$
    create policy sf_github_deliveries_select on public.sf_github_deliveries for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_automation_runs' and policyname='sf_automation_runs_select') then execute $p$
    create policy sf_automation_runs_select on public.sf_automation_runs for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
end $$;
grant select, insert, update, delete on public.sf_automations to authenticated;
grant select on public.sf_automation_runs, public.sf_github_deliveries to authenticated;
