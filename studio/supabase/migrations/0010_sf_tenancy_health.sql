-- 0010_sf_tenancy_health.sql — found by the portal's own scorecard (tenancy audit, key: workspace_id):
--   * child tables carry workspace_id directly (defence in depth + workspace-leading indexes), always DERIVED from the
--     parent by a trigger — callers never supply it, so it cannot be spoofed and app code is unchanged
--   * sf_api_keys gets a workspace-leading index
--   * sf_health_ping(): the deep health check's database probe over the anon role (returns 1, reads nothing)
-- Note: sf_files and sf_approvals are immutable/append-only by trigger; those guards are paused ONLY while this
-- migration fills the derived column (same transaction), then re-enabled. Idempotent; sf_ prefix only.
-- rollback: (manual — the columns go with their tables in 0001/0003/0004 rollbacks)
--   drop function if exists public.sf_health_ping();
--   drop function if exists public.sf_derive_workspace() cascade;

create or replace function public.sf_health_ping() returns int language sql stable security definer set search_path = public as $$ select 1 $$;
revoke all on function public.sf_health_ping() from public;
grant execute on function public.sf_health_ping() to anon, authenticated;

-- workspace_id derived from the parent row; TG_ARGV[0] names the parent kind
create or replace function public.sf_derive_workspace() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  case tg_argv[0]
    when 'skill'   then select s.workspace_id into new.workspace_id from public.sf_skills s where s.id = new.skill_id;
    when 'version' then select s.workspace_id into new.workspace_id from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = new.version_id;
    when 'agent'   then select a.workspace_id into new.workspace_id from public.sf_agents a where a.id = new.agent_id;
    when 'talent'  then select t.workspace_id into new.workspace_id from public.sf_talent t where t.id = new.talent_id;
  end case;
  if new.workspace_id is null then raise exception '%: parent row not found', tg_table_name using errcode = 'foreign_key_violation'; end if;
  return new;
end $$;

-- explicit per table (reviewable, and visible to static audits)
alter table public.sf_skill_versions add column if not exists workspace_id uuid references public.sf_workspaces(id) on delete cascade;
alter table public.sf_files add column if not exists workspace_id uuid references public.sf_workspaces(id) on delete cascade;
alter table public.sf_eval_cases add column if not exists workspace_id uuid references public.sf_workspaces(id) on delete cascade;
alter table public.sf_eval_runs add column if not exists workspace_id uuid references public.sf_workspaces(id) on delete cascade;
alter table public.sf_approvals add column if not exists workspace_id uuid references public.sf_workspaces(id) on delete cascade;
alter table public.sf_agent_versions add column if not exists workspace_id uuid references public.sf_workspaces(id) on delete cascade;
alter table public.sf_talent_versions add column if not exists workspace_id uuid references public.sf_workspaces(id) on delete cascade;

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_skill_versions_derive_workspace') then
    create trigger sf_skill_versions_derive_workspace before insert or update of skill_id on public.sf_skill_versions for each row execute function public.sf_derive_workspace('skill'); end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_files_derive_workspace') then
    create trigger sf_files_derive_workspace before insert or update of version_id on public.sf_files for each row execute function public.sf_derive_workspace('version'); end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_eval_cases_derive_workspace') then
    create trigger sf_eval_cases_derive_workspace before insert or update of version_id on public.sf_eval_cases for each row execute function public.sf_derive_workspace('version'); end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_eval_runs_derive_workspace') then
    create trigger sf_eval_runs_derive_workspace before insert or update of version_id on public.sf_eval_runs for each row execute function public.sf_derive_workspace('version'); end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_approvals_derive_workspace') then
    create trigger sf_approvals_derive_workspace before insert or update of version_id on public.sf_approvals for each row execute function public.sf_derive_workspace('version'); end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_agent_versions_derive_workspace') then
    create trigger sf_agent_versions_derive_workspace before insert or update of agent_id on public.sf_agent_versions for each row execute function public.sf_derive_workspace('agent'); end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_talent_versions_derive_workspace') then
    create trigger sf_talent_versions_derive_workspace before insert or update of talent_id on public.sf_talent_versions for each row execute function public.sf_derive_workspace('talent'); end if;
end $$;

-- fill the derived column for existing rows (guards paused only where the table is immutable by design)
alter table public.sf_files disable trigger sf_files_guard;
alter table public.sf_approvals disable trigger sf_approvals_append_only;
update public.sf_skill_versions v set workspace_id = s.workspace_id from public.sf_skills s where s.id = v.skill_id and v.workspace_id is null;
update public.sf_files f set workspace_id = v.workspace_id from public.sf_skill_versions v where v.id = f.version_id and f.workspace_id is null;
update public.sf_eval_cases c set workspace_id = v.workspace_id from public.sf_skill_versions v where v.id = c.version_id and c.workspace_id is null;
update public.sf_eval_runs r set workspace_id = v.workspace_id from public.sf_skill_versions v where v.id = r.version_id and r.workspace_id is null;
update public.sf_approvals a set workspace_id = v.workspace_id from public.sf_skill_versions v where v.id = a.version_id and a.workspace_id is null;
update public.sf_agent_versions v set workspace_id = a.workspace_id from public.sf_agents a where a.id = v.agent_id and v.workspace_id is null;
update public.sf_talent_versions v set workspace_id = t.workspace_id from public.sf_talent t where t.id = v.talent_id and v.workspace_id is null;
alter table public.sf_files enable trigger sf_files_guard;
alter table public.sf_approvals enable trigger sf_approvals_append_only;

alter table public.sf_skill_versions alter column workspace_id set not null;
alter table public.sf_files alter column workspace_id set not null;
alter table public.sf_eval_cases alter column workspace_id set not null;
alter table public.sf_eval_runs alter column workspace_id set not null;
alter table public.sf_approvals alter column workspace_id set not null;
alter table public.sf_agent_versions alter column workspace_id set not null;
alter table public.sf_talent_versions alter column workspace_id set not null;

create index if not exists sf_skill_versions_ws_idx on public.sf_skill_versions (workspace_id, skill_id);
create index if not exists sf_files_ws_idx on public.sf_files (workspace_id, version_id);
create index if not exists sf_eval_cases_ws_idx on public.sf_eval_cases (workspace_id, version_id);
create index if not exists sf_eval_runs_ws_idx on public.sf_eval_runs (workspace_id, version_id);
create index if not exists sf_approvals_ws_idx on public.sf_approvals (workspace_id, version_id);
create index if not exists sf_agent_versions_ws_idx on public.sf_agent_versions (workspace_id, agent_id);
create index if not exists sf_talent_versions_ws_idx on public.sf_talent_versions (workspace_id, talent_id);
create index if not exists sf_api_keys_ws_idx on public.sf_api_keys (workspace_id, created_at desc);
