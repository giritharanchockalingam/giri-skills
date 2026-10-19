-- 0014_sf_actions.sql — self-service actions: run a library skill on a catalog repository's real files, with an
-- approval rule set by workspace policy, and every request recorded (who asked, who decided, the run it produced).
-- Rules live in the database, not the UI: a request can only be created through sf_action_request (which decides
-- from policy whether approval is needed), decided through sf_action_decide (reviewer/admin, never the requester),
-- and moved through execution by sf_action_mark (valid transitions only). No direct writes. sf_ prefix; idempotent.
-- rollback: (manual — drops the action log and the policy column; runs it produced stay in sf_runs)
--   drop function if exists public.sf_action_mark(uuid, text, uuid, text, text);
--   drop function if exists public.sf_action_decide(uuid, boolean, text);
--   drop function if exists public.sf_action_request(uuid, text, text, jsonb, boolean, text);
--   drop table if exists public.sf_action_runs cascade;
--   alter table if exists public.sf_policies drop column if exists action_approval;

alter table public.sf_policies add column if not exists action_approval text not null default 'model_steps'
  check (action_approval in ('none', 'model_steps', 'always'));   -- when a self-service action needs a reviewer's approval

create table if not exists public.sf_action_runs (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  entity_id     uuid references public.sf_catalog_entities(id) on delete set null,
  repo          text not null check (repo ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
  skill         text not null check (skill ~ '^[a-z0-9-]+$'),             -- workspace skill slug
  inputs        jsonb not null default '{}'::jsonb,                        -- folder paths and values asked for (never file contents)
  uses_model    boolean not null default false,
  reason        text not null default '' check (length(reason) <= 1000),
  status        text not null check (status in ('pending_approval', 'approved', 'rejected', 'running', 'succeeded', 'failed')),
  requested_by  uuid not null references auth.users(id),
  decided_by    uuid references auth.users(id),
  decided_at    timestamptz,
  decision_note text check (decision_note is null or length(decision_note) <= 1000),
  run_id        uuid references public.sf_runs(id) on delete set null,
  commit_sha    text check (commit_sha is null or commit_sha ~ '^[0-9a-f]{40}$'),
  error         text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists sf_action_runs_ws_idx on public.sf_action_runs (workspace_id, created_at desc);
create index if not exists sf_action_runs_pending_idx on public.sf_action_runs (workspace_id) where status = 'pending_approval';
do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_action_runs_updated_at') then
    create trigger sf_action_runs_updated_at before update on public.sf_action_runs for each row execute function public.sf_set_updated_at(); end if;
end $$;

alter table public.sf_action_runs enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_action_runs' and policyname='sf_action_runs_select') then execute $p$
    create policy sf_action_runs_select on public.sf_action_runs for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
end $$;
grant select on public.sf_action_runs to authenticated;     -- writes only through the functions below

-- Request an action. Approval is decided here from policy, so no client can skip it.
create or replace function public.sf_action_request(p_workspace uuid, p_repo text, p_skill text, p_inputs jsonb, p_uses_model boolean, p_reason text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_rule text; v_status text; v_id uuid; v_entity uuid;
begin
  if auth.uid() is null or not public.sf_is_member(p_workspace) then
    raise exception 'not a member of this workspace' using errcode = 'insufficient_privilege';
  end if;
  select id into v_entity from public.sf_catalog_entities where workspace_id = p_workspace and lower(key) = lower(p_repo) and kind = 'repository';
  if v_entity is null then raise exception 'repository % is not in this workspace''s catalog', p_repo using errcode = 'check_violation'; end if;
  select coalesce((select action_approval from public.sf_policies where workspace_id = p_workspace), 'model_steps') into v_rule;
  v_status := case when v_rule = 'always' or (v_rule = 'model_steps' and coalesce(p_uses_model, false)) then 'pending_approval' else 'approved' end;
  insert into public.sf_action_runs (workspace_id, entity_id, repo, skill, inputs, uses_model, reason, status, requested_by)
  values (p_workspace, v_entity, p_repo, p_skill, coalesce(p_inputs, '{}'::jsonb), coalesce(p_uses_model, false), left(coalesce(p_reason, ''), 1000), v_status, auth.uid())
  returning id into v_id;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (p_workspace, auth.uid(), 'user', 'action.request', 'action', v_id::text, jsonb_build_object('repo', p_repo, 'skill', p_skill, 'status', v_status, 'rule', v_rule));
  return jsonb_build_object('id', v_id, 'status', v_status, 'rule', v_rule);
end $$;

-- Approve or reject a pending request: reviewers and admins only, and never your own request.
create or replace function public.sf_action_decide(p_id uuid, p_approve boolean, p_note text)
returns text language plpgsql security definer set search_path = public as $$
declare a public.sf_action_runs; v_status text;
begin
  select * into a from public.sf_action_runs where id = p_id for update;
  if a.id is null or not public.sf_is_member(a.workspace_id) then raise exception 'action not found' using errcode = 'no_data_found'; end if;
  if not public.sf_has_role(a.workspace_id, array['reviewer', 'admin']) then
    raise exception 'only reviewers and admins decide actions' using errcode = 'insufficient_privilege'; end if;
  if a.requested_by = auth.uid() then raise exception 'you cannot decide your own request' using errcode = 'insufficient_privilege'; end if;
  if a.status <> 'pending_approval' then raise exception 'this action is already %', a.status using errcode = 'check_violation'; end if;
  v_status := case when p_approve then 'approved' else 'rejected' end;
  update public.sf_action_runs set status = v_status, decided_by = auth.uid(), decided_at = now(), decision_note = nullif(left(coalesce(p_note, ''), 1000), '') where id = p_id;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (a.workspace_id, auth.uid(), 'user', 'action.' || case when p_approve then 'approve' else 'reject' end, 'action', p_id::text, jsonb_build_object('note', p_note));
  return v_status;
end $$;

-- Execution progress: approved → running → succeeded|failed, by the requester or the approver.
create or replace function public.sf_action_mark(p_id uuid, p_status text, p_run uuid, p_error text, p_commit text default null)
returns text language plpgsql security definer set search_path = public as $$
declare a public.sf_action_runs;
begin
  select * into a from public.sf_action_runs where id = p_id for update;
  if a.id is null or not public.sf_is_member(a.workspace_id) then raise exception 'action not found' using errcode = 'no_data_found'; end if;
  if auth.uid() not in (a.requested_by, coalesce(a.decided_by, a.requested_by)) then
    raise exception 'only the requester or the approver runs an action' using errcode = 'insufficient_privilege'; end if;
  if not ((a.status = 'approved' and p_status = 'running') or (a.status = 'running' and p_status in ('succeeded', 'failed'))) then
    raise exception 'cannot move an action from % to %', a.status, p_status using errcode = 'check_violation'; end if;
  update public.sf_action_runs set status = p_status, run_id = coalesce(p_run, run_id), error = left(p_error, 2000),
    commit_sha = coalesce(p_commit, commit_sha) where id = p_id;
  if p_status in ('succeeded', 'failed') then
    insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
    values (a.workspace_id, auth.uid(), 'user', 'action.finish', 'action', p_id::text, jsonb_build_object('status', p_status, 'run_id', p_run, 'error', left(p_error, 300)));
  end if;
  return p_status;
end $$;
grant execute on function public.sf_action_request(uuid, text, text, jsonb, boolean, text) to authenticated;
grant execute on function public.sf_action_decide(uuid, boolean, text) to authenticated;
grant execute on function public.sf_action_mark(uuid, text, uuid, text, text) to authenticated;
revoke execute on function public.sf_action_request(uuid, text, text, jsonb, boolean, text) from anon, public;
revoke execute on function public.sf_action_decide(uuid, boolean, text) from anon, public;
revoke execute on function public.sf_action_mark(uuid, text, uuid, text, text) from anon, public;
