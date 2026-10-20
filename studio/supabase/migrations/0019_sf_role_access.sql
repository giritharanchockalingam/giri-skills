-- 0019: roles decide who can run which skill (docs/ACCESS-BY-ROLE.md).
-- A workspace policy, skills_by_role, OFF by default (behaviour unchanged until an admin turns it on). When on, a
-- consumer or an API key may run a published skill only if a role assigned to it (published role version) lists the
-- skill (library id or workspace slug). Authors, reviewers and admins are not restricted: they test before release.
-- Enforced in one function (sf_run_access) used by both run RPCs and by a BEFORE INSERT backstop on sf_runs, so the
-- portal, API, MCP, Port and direct inserts all hit the same rule. Refusals through the RPCs are audited (run.denied)
-- and answered as {"error":"not_in_role"} so the audit row commits. sf_ prefix only; idempotent.
-- rollback: (manual — in this order; then re-run sf_run_insert and sf_record_run from 0002_sf_functions.sql)
--   drop function if exists public.sf_playbook_access(uuid, text);
--   drop function if exists public.sf_runs_role_guard() cascade;
--   drop table if exists public.sf_role_assignments cascade;
--   drop function if exists public.sf_role_assignment_guard() cascade;
--   drop function if exists public.sf_run_access(uuid, uuid, uuid, uuid);
--   alter table public.sf_runs drop column if exists granted_by_role;
--   alter table public.sf_policies drop column if exists skills_by_role;

alter table public.sf_policies add column if not exists skills_by_role boolean not null default false;

create table if not exists public.sf_role_assignments (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  talent_id     uuid not null references public.sf_talent(id) on delete cascade,
  user_id       uuid references auth.users(id) on delete cascade,
  api_key_id    uuid references public.sf_api_keys(id) on delete cascade,
  granted_by    uuid not null references auth.users(id),
  created_at    timestamptz not null default now(),
  check (num_nonnulls(user_id, api_key_id) = 1)
);
create unique index if not exists sf_role_assignments_user_uq on public.sf_role_assignments(talent_id, user_id) where user_id is not null;
create unique index if not exists sf_role_assignments_key_uq on public.sf_role_assignments(talent_id, api_key_id) where api_key_id is not null;
create index if not exists sf_role_assignments_ws_idx on public.sf_role_assignments(workspace_id);

alter table public.sf_runs add column if not exists granted_by_role uuid references public.sf_talent(id) on delete set null;

-- an assignment stays inside one workspace: a role of this workspace, a member or a key of this workspace
create or replace function public.sf_role_assignment_guard() returns trigger language plpgsql set search_path = public as $$
begin
  if not exists (select 1 from public.sf_talent t where t.id = new.talent_id and t.workspace_id = new.workspace_id and t.kind = 'role') then
    raise exception 'role must be a role of this workspace' using errcode = 'check_violation'; end if;
  if new.user_id is not null and not exists (select 1 from public.sf_memberships m where m.workspace_id = new.workspace_id and m.user_id = new.user_id) then
    raise exception 'user must be a member of this workspace' using errcode = 'check_violation'; end if;
  if new.api_key_id is not null and not exists (select 1 from public.sf_api_keys k where k.id = new.api_key_id and k.workspace_id = new.workspace_id) then
    raise exception 'API key must belong to this workspace' using errcode = 'check_violation'; end if;
  return new;
end $$;
do $$ begin if not exists (select 1 from pg_trigger where tgname = 'sf_role_assignments_guard') then
  create trigger sf_role_assignments_guard before insert or update on public.sf_role_assignments for each row execute function public.sf_role_assignment_guard(); end if; end $$;

alter table public.sf_role_assignments enable row level security;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_role_assignments' and policyname='sf_role_assignments_select') then execute $p$ create policy sf_role_assignments_select on public.sf_role_assignments for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_role_assignments' and policyname='sf_role_assignments_insert') then execute $p$ create policy sf_role_assignments_insert on public.sf_role_assignments for insert to authenticated with check (public.sf_has_role(workspace_id, array['admin']) and granted_by = auth.uid()) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_role_assignments' and policyname='sf_role_assignments_delete') then execute $p$ create policy sf_role_assignments_delete on public.sf_role_assignments for delete to authenticated using (public.sf_has_role(workspace_id, array['admin'])) $p$; end if; end $$;
grant select, insert, delete on public.sf_role_assignments to authenticated;

-- The one rule. Internal only (no grant): callers pass a holder, so exposing it would reveal other people's access.
create or replace function public.sf_run_access(p_ws uuid, p_version uuid, p_user uuid, p_key uuid)
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare v_on boolean; v_role text; v_keys text[]; g record;
begin
  select p.skills_by_role into v_on from public.sf_policies p where p.workspace_id = p_ws;
  if not coalesce(v_on, false) then return jsonb_build_object('allowed', true, 'reason', 'policy_off'); end if;
  if p_user is not null then
    select m.role into v_role from public.sf_memberships m where m.workspace_id = p_ws and m.user_id = p_user;
    if v_role in ('author', 'reviewer', 'admin') then return jsonb_build_object('allowed', true, 'reason', 'builder'); end if;
  end if;
  if p_user is null and p_key is null then return jsonb_build_object('allowed', false, 'reason', 'not_in_role'); end if;
  select array_remove(array[v.source->>'repo_skill', s.slug], null) into v_keys
    from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = p_version and s.workspace_id = p_ws;
  select t.id, t.slug, t.name into g
    from public.sf_role_assignments a
    join public.sf_talent t on t.id = a.talent_id and t.kind = 'role'
    join public.sf_talent_versions tv on tv.talent_id = t.id and tv.status = 'published'
   where a.workspace_id = p_ws
     and ((p_user is not null and a.user_id = p_user) or (p_key is not null and a.api_key_id = p_key))
     and coalesce(v_keys, '{}') <> '{}' and (tv.spec->'skills') ?| v_keys
   order by t.slug limit 1;
  if not found then return jsonb_build_object('allowed', false, 'reason', 'not_in_role'); end if;
  return jsonb_build_object('allowed', true, 'reason', 'role', 'role_id', g.id, 'role_slug', g.slug, 'role_name', g.name);
end $$;
revoke all on function public.sf_run_access(uuid, uuid, uuid, uuid) from public, anon, authenticated;

-- Backstop for every insert path (RPCs and the direct RLS insert): refuse, and record which role allowed the run.
create or replace function public.sf_runs_role_guard() returns trigger language plpgsql security definer set search_path = public as $$
declare acc jsonb;
begin
  acc := public.sf_run_access(new.workspace_id, new.version_id, new.invoked_by, new.api_key_id);
  if not (acc->>'allowed')::boolean then
    raise exception 'not_in_role: this skill is not in any role assigned to you' using errcode = 'insufficient_privilege';
  end if;
  new.granted_by_role := coalesce(new.granted_by_role, (acc->>'role_id')::uuid);
  return new;
end $$;
revoke all on function public.sf_runs_role_guard() from public, anon, authenticated;   -- trigger use only
do $$ begin if not exists (select 1 from pg_trigger where tgname = 'sf_runs_role_guard') then
  create trigger sf_runs_role_guard before insert on public.sf_runs for each row execute function public.sf_runs_role_guard(); end if; end $$;

-- ── run RPCs (from 0002), now checking access first so a refusal is audited and answered, not raised ──
create or replace function public.sf_run_insert(p_version uuid, p_source text, p_inputs_ref jsonb, p_idempotency_key text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v record; pol record; v_running int; v_spend numeric; v_existing uuid; v_id uuid; v_role text; v_acc jsonb;
begin
  select v2.*, s.workspace_id, s.slug into v from public.sf_skill_versions v2 join public.sf_skills s on s.id = v2.skill_id where v2.id = p_version;
  if v is null then raise exception 'version not found' using errcode = 'no_data_found'; end if;
  v_role := public.sf_role(v.workspace_id);
  if v_role is null then raise exception 'not a member of this workspace' using errcode = 'insufficient_privilege'; end if;
  if v.status <> 'published' and v_role = 'consumer' then
    raise exception 'consumers can only run published versions (this one is %)', v.status using errcode = 'insufficient_privilege';
  end if;
  if v.status in ('retired','superseded') then
    raise exception 'version is % and cannot be run', v.status using errcode = 'check_violation';
  end if;
  v_acc := public.sf_run_access(v.workspace_id, p_version, auth.uid(), null);
  if not (v_acc->>'allowed')::boolean then
    insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
    values (v.workspace_id, auth.uid(), 'user', 'run.denied', 'skill', v.slug, jsonb_build_object('version_id', p_version, 'source', p_source, 'reason', v_acc->>'reason'));
    return jsonb_build_object('error', 'not_in_role', 'message', 'This skill is not in any role assigned to you. Ask an administrator for access.');
  end if;
  if p_idempotency_key is not null then
    select id into v_existing from public.sf_runs where workspace_id = v.workspace_id and idempotency_key = p_idempotency_key;
    if v_existing is not null then return jsonb_build_object('run_id', v_existing, 'existing', true); end if;
  end if;
  select * into pol from public.sf_policies where workspace_id = v.workspace_id;
  select count(*) into v_running from public.sf_runs where workspace_id = v.workspace_id and status in ('queued','running')
    and created_at > now() - interval '10 minutes';
  if pol.workspace_id is not null and v_running >= pol.max_concurrency then
    raise exception 'concurrency limit reached: % run(s) in progress, policy allows %', v_running, pol.max_concurrency using errcode = 'check_violation';
  end if;
  if pol.workspace_id is not null and pol.monthly_budget_usd is not null then
    select coalesce(sum(cost_usd), 0) into v_spend from public.sf_runs where workspace_id = v.workspace_id and created_at >= date_trunc('month', now());
    if v_spend >= pol.monthly_budget_usd then
      raise exception 'monthly budget reached: estimated spend % USD of % USD', round(v_spend, 4), pol.monthly_budget_usd using errcode = 'check_violation';
    end if;
  end if;
  insert into public.sf_runs (workspace_id, version_id, invoked_by, source, status, idempotency_key, inputs_ref, granted_by_role)
  values (v.workspace_id, p_version, auth.uid(), p_source, 'queued', p_idempotency_key, coalesce(p_inputs_ref, '[]'::jsonb), (v_acc->>'role_id')::uuid)
  returning id into v_id;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v.workspace_id, auth.uid(), 'user', 'run.create', 'run', v_id::text,
          jsonb_build_object('version_id', p_version, 'source', p_source) || case when v_acc ? 'role_slug' then jsonb_build_object('role', v_acc->>'role_slug') else '{}'::jsonb end);
  return jsonb_build_object('run_id', v_id, 'existing', false, 'workspace_id', v.workspace_id);
end $$;
grant execute on function public.sf_run_insert(uuid, text, jsonb, text) to authenticated;

create or replace function public.sf_record_run(p_key_hash text, p_slug text, p_inputs_ref jsonb, p_idempotency_key text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; v record; pol record; v_running int; v_spend numeric; v_existing uuid; v_id uuid; v_acc jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select v2.*, s.workspace_id into v from public.sf_skills s join public.sf_skill_versions v2 on v2.id = s.latest_version_id
   where s.workspace_id = v_ws and s.slug = p_slug and s.status = 'published' and v2.status = 'published';
  if v is null then raise exception 'no published version' using errcode = 'no_data_found'; end if;
  v_acc := public.sf_run_access(v_ws, v.id, null, v_key);
  if not (v_acc->>'allowed')::boolean then
    insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
    values (v_ws, v_key, 'api_key', 'run.denied', 'skill', p_slug, jsonb_build_object('version_id', v.id, 'source', 'api', 'reason', v_acc->>'reason'));
    return jsonb_build_object('error', 'not_in_role', 'message', 'This skill is not in any role assigned to this API key. Ask an administrator to assign one.');
  end if;
  if p_idempotency_key is not null then
    select id into v_existing from public.sf_runs where workspace_id = v_ws and idempotency_key = p_idempotency_key;
    if v_existing is not null then return jsonb_build_object('run_id', v_existing, 'existing', true, 'version_id', v.id); end if;
  end if;
  select * into pol from public.sf_policies where workspace_id = v_ws;
  select count(*) into v_running from public.sf_runs where workspace_id = v_ws and status in ('queued','running') and created_at > now() - interval '10 minutes';
  if pol.workspace_id is not null and v_running >= pol.max_concurrency then
    raise exception 'concurrency limit reached: % run(s) in progress, policy allows %', v_running, pol.max_concurrency using errcode = 'check_violation';
  end if;
  if pol.workspace_id is not null and pol.monthly_budget_usd is not null then
    select coalesce(sum(cost_usd), 0) into v_spend from public.sf_runs where workspace_id = v_ws and created_at >= date_trunc('month', now());
    if v_spend >= pol.monthly_budget_usd then
      raise exception 'monthly budget reached: estimated spend % USD of % USD', round(v_spend, 4), pol.monthly_budget_usd using errcode = 'check_violation';
    end if;
  end if;
  insert into public.sf_runs (workspace_id, version_id, api_key_id, source, status, idempotency_key, inputs_ref, granted_by_role)
  values (v_ws, v.id, v_key, 'api', 'queued', p_idempotency_key, coalesce(p_inputs_ref, '[]'::jsonb), (v_acc->>'role_id')::uuid) returning id into v_id;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v_ws, v_key, 'api_key', 'run.create', 'run', v_id::text,
          jsonb_build_object('version_id', v.id, 'source', 'api', 'slug', p_slug) || case when v_acc ? 'role_slug' then jsonb_build_object('role', v_acc->>'role_slug') else '{}'::jsonb end);
  return jsonb_build_object('run_id', v_id, 'existing', false, 'version_id', v.id, 'workspace_id', v_ws, 'manifest', v.manifest, 'source', v.source, 'version', v.version);
end $$;
grant execute on function public.sf_record_run(text, text, jsonb, text) to anon, authenticated;

-- Playbooks: a consumer may start a published playbook only if an assigned role lists it (same policy switch).
-- Answers for the caller only (auth.uid()), so it is safe to grant.
create or replace function public.sf_playbook_access(p_ws uuid, p_agent_slug text)
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare v_on boolean; v_role text; g record;
begin
  v_role := public.sf_role(p_ws);
  if v_role is null then return jsonb_build_object('allowed', false, 'reason', 'not_member'); end if;
  select p.skills_by_role into v_on from public.sf_policies p where p.workspace_id = p_ws;
  if not coalesce(v_on, false) then return jsonb_build_object('allowed', true, 'reason', 'policy_off'); end if;
  if v_role in ('author', 'reviewer', 'admin') then return jsonb_build_object('allowed', true, 'reason', 'builder'); end if;
  select t.id, t.slug into g
    from public.sf_role_assignments a
    join public.sf_talent t on t.id = a.talent_id and t.kind = 'role'
    join public.sf_talent_versions tv on tv.talent_id = t.id and tv.status = 'published'
   where a.workspace_id = p_ws and a.user_id = auth.uid() and (tv.spec->'playbooks') ? p_agent_slug
   order by t.slug limit 1;
  if not found then return jsonb_build_object('allowed', false, 'reason', 'not_in_role'); end if;
  return jsonb_build_object('allowed', true, 'reason', 'role', 'role_id', g.id, 'role_slug', g.slug);
end $$;
revoke all on function public.sf_playbook_access(uuid, text) from public, anon;
grant execute on function public.sf_playbook_access(uuid, text) to authenticated;
