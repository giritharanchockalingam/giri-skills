-- 0009_sf_insights.sql — what the Insights dashboard needs beyond existing run tables:
--   sf_browser_runs   skills run in the browser (Pyodide): metadata only — never inputs or outputs
--   sf_roi_baselines  the workspace's OWN statement of what a skill's task takes by hand (minutes, optional rate),
--                     with owner and source. ROI is computed only where a baseline exists; nothing is assumed.
-- sf_ prefix only; idempotent.
-- rollback: (manual — drops browser-run metadata and the ROI baselines)
--   drop table if exists public.sf_roi_baselines cascade;
--   drop table if exists public.sf_browser_runs cascade;

create table if not exists public.sf_browser_runs (
  id             uuid primary key default gen_random_uuid(),
  workspace_id   uuid not null references public.sf_workspaces(id) on delete cascade,
  user_id        uuid not null references auth.users(id),
  skill          text not null check (skill ~ '^[a-z0-9-]+/[a-z0-9-]+$'),
  status         text not null check (status in ('succeeded', 'failed', 'needs_input')),
  example        boolean not null default false,                  -- ran on the skill's own sample inputs (a demo, not work)
  mode           text check (mode is null or mode in ('new', 'existing')),
  checks_passed  int check (checks_passed is null or checks_passed >= 0),
  checks_total   int check (checks_total is null or checks_total >= 0),
  duration_ms    int check (duration_ms is null or duration_ms >= 0),
  created_at     timestamptz not null default now()
);
create index if not exists sf_browser_runs_ws_idx on public.sf_browser_runs(workspace_id, created_at desc);

create table if not exists public.sf_roi_baselines (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references public.sf_workspaces(id) on delete cascade,
  skill            text not null check (skill ~ '^[a-z0-9-]+/[a-z0-9-]+$'),
  manual_minutes   numeric(8,1) not null check (manual_minutes > 0 and manual_minutes <= 10000),
  hourly_rate_usd  numeric(8,2) check (hourly_rate_usd is null or (hourly_rate_usd > 0 and hourly_rate_usd <= 2000)),
  owner            text not null check (length(owner) between 1 and 120),        -- who stands behind the number
  source           text not null check (length(source) between 3 and 300),       -- how it was measured
  set_by           uuid not null references auth.users(id),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (workspace_id, skill)
);

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_roi_baselines_updated_at') then
    create trigger sf_roi_baselines_updated_at before update on public.sf_roi_baselines for each row execute function public.sf_set_updated_at(); end if;
end $$;

alter table public.sf_browser_runs  enable row level security;
alter table public.sf_roi_baselines enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_browser_runs' and policyname='sf_browser_runs_select') then execute $p$
    create policy sf_browser_runs_select on public.sf_browser_runs for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_browser_runs' and policyname='sf_browser_runs_insert') then execute $p$
    create policy sf_browser_runs_insert on public.sf_browser_runs for insert to authenticated
    with check (public.sf_is_member(workspace_id) and user_id = auth.uid()) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_roi_baselines' and policyname='sf_roi_select') then execute $p$
    create policy sf_roi_select on public.sf_roi_baselines for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_roi_baselines' and policyname='sf_roi_write') then execute $p$
    create policy sf_roi_write on public.sf_roi_baselines for all to authenticated
    using (public.sf_has_role(workspace_id, array['admin'])) with check (public.sf_has_role(workspace_id, array['admin']) and set_by = auth.uid()) $p$; end if;
end $$;
grant select, insert on public.sf_browser_runs to authenticated;
grant select, insert, update, delete on public.sf_roi_baselines to authenticated;
