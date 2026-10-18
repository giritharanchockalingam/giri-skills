-- 0002_sf_functions.sql — release-state view, lifecycle RPCs, API-key RPCs, audit helper (idempotent).
-- Every RPC that changes lifecycle state runs as SECURITY DEFINER and sets the transaction-local flag
-- sf.rpc = '1' so the sf_versions_guard trigger lets the transition through. Role checks are inside.

-- ───────────────────────────── audit ─────────────────────────────
create or replace function public.sf_audit(p_workspace uuid, p_action text, p_entity_type text, p_entity_id text, p_details jsonb default '{}'::jsonb)
returns bigint language plpgsql security definer set search_path = public as $$
declare v_id bigint;
begin
  if auth.uid() is null or not public.sf_is_member(p_workspace) then
    raise exception 'not a member of this workspace' using errcode = 'insufficient_privilege';
  end if;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (p_workspace, auth.uid(), 'user', p_action, p_entity_type, p_entity_id, coalesce(p_details, '{}'::jsonb))
  returning id into v_id;
  return v_id;
end $$;
grant execute on function public.sf_audit(uuid, text, text, text, jsonb) to authenticated;

-- ───────────────────────────── workspace bootstrap ─────────────────────────────
-- The user who creates a workspace becomes its admin. A default policy row is created with it.
create or replace function public.sf_create_workspace(p_name text, p_slug text)
returns uuid language plpgsql security definer set search_path = public as $$
declare v_ws uuid;
begin
  if auth.uid() is null then raise exception 'sign in first' using errcode = 'insufficient_privilege'; end if;
  insert into public.sf_workspaces (name, slug, created_by) values (p_name, p_slug, auth.uid()) returning id into v_ws;
  insert into public.sf_memberships (workspace_id, user_id, role) values (v_ws, auth.uid(), 'admin');
  insert into public.sf_policies (workspace_id) values (v_ws);
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v_ws, auth.uid(), 'user', 'workspace.create', 'workspace', v_ws::text, jsonb_build_object('name', p_name, 'slug', p_slug));
  return v_ws;
end $$;
grant execute on function public.sf_create_workspace(text, text) to authenticated;

-- Email lookup for the admin "add member" form: reads auth.users, only for admins of some workspace.
create or replace function public.sf_user_id_by_email(p_email text)
returns uuid language plpgsql security definer set search_path = public as $$
declare v_id uuid;
begin
  if not exists (select 1 from public.sf_memberships where user_id = auth.uid() and role = 'admin') then
    raise exception 'admins only' using errcode = 'insufficient_privilege';
  end if;
  select id into v_id from auth.users where lower(email) = lower(trim(p_email)) limit 1;
  return v_id;
end $$;
grant execute on function public.sf_user_id_by_email(text) to authenticated;

-- Member roster with emails (auth.users is not readable by clients). Members of the workspace only.
create or replace function public.sf_member_directory(p_workspace uuid)
returns table (user_id uuid, email text, role text, created_at timestamptz)
language sql security definer set search_path = public stable as $$
  select m.user_id, u.email::text, m.role, m.created_at
  from public.sf_memberships m join auth.users u on u.id = m.user_id
  where m.workspace_id = p_workspace and public.sf_is_member(p_workspace)
  order by m.created_at
$$;
grant execute on function public.sf_member_directory(uuid) to authenticated;

-- ───────────────────────────── evaluation set hash ─────────────────────────────
-- Deterministic hash of a version's current evaluation cases (ordered by id); stored on every eval run so
-- a later change to the cases makes the stored evidence visibly outdated.
create or replace function public.sf_eval_set_hash(p_version uuid)
returns text language sql stable security definer set search_path = public as $$
  select encode(sha256(convert_to(coalesce(string_agg(
           c.id::text || '|' || c.name || '|' || c.inputs::text || '|' || c.checks::text || '|' || c.expected::text,
           E'\n' order by c.id), ''), 'UTF8')), 'hex')
  from public.sf_eval_cases c where c.version_id = p_version
$$;
grant execute on function public.sf_eval_set_hash(uuid) to authenticated;

-- ───────────────────────────── release state ─────────────────────────────
drop view if exists public.sf_version_release_state;
create view public.sf_version_release_state with (security_invoker = true) as
with latest_eval as (
  select distinct on (version_id) version_id, pass_rate, eval_set_hash, finished_at, status, provider, model, id as eval_run_id
  from public.sf_eval_runs where status = 'finished' order by version_id, finished_at desc nulls last
),
latest_approval as (
  select distinct on (version_id) version_id, decision, manifest_hash, created_at, reviewer_id, note, id as approval_id
  from public.sf_approvals order by version_id, created_at desc
),
case_counts as (
  select version_id, count(*)::int as n from public.sf_eval_cases group by version_id
)
select
  v.id as version_id, v.skill_id, s.workspace_id, v.version, v.status, v.manifest_hash,
  (v.manifest #>> '{release_criteria,min_eval_pass_rate}')::numeric as min_eval_pass_rate,
  coalesce((v.manifest #>> '{release_criteria,require_approval}')::boolean, true) as require_approval,
  coalesce(cc.n, 0) as eval_case_count,
  public.sf_eval_set_hash(v.id) as current_eval_set_hash,
  le.eval_run_id as latest_eval_run_id, le.pass_rate as latest_eval_pass_rate, le.eval_set_hash as latest_eval_set_hash,
  le.finished_at as latest_eval_at, le.provider as latest_eval_provider, le.model as latest_eval_model,
  (le.eval_set_hash is not null and le.eval_set_hash = public.sf_eval_set_hash(v.id)) as eval_current,
  case
    when (v.manifest #>> '{release_criteria,min_eval_pass_rate}') is null
      or (v.manifest #>> '{release_criteria,min_eval_pass_rate}')::numeric <= 0 then true
    when coalesce(cc.n, 0) = 0 then false
    when le.eval_set_hash is null or le.eval_set_hash <> public.sf_eval_set_hash(v.id) then false
    else le.pass_rate >= (v.manifest #>> '{release_criteria,min_eval_pass_rate}')::numeric
  end as eval_gate_met,
  la.approval_id as latest_approval_id, la.decision as latest_approval_decision, la.manifest_hash as latest_approval_hash,
  la.created_at as latest_approval_at, la.reviewer_id as latest_approval_reviewer, la.note as latest_approval_note,
  (la.decision = 'approve' and la.manifest_hash = v.manifest_hash) as approval_valid,
  (la.decision = 'approve' and la.manifest_hash <> v.manifest_hash) as approval_stale,
  (
    (case
      when (v.manifest #>> '{release_criteria,min_eval_pass_rate}') is null
        or (v.manifest #>> '{release_criteria,min_eval_pass_rate}')::numeric <= 0 then true
      when coalesce(cc.n, 0) = 0 then false
      when le.eval_set_hash is null or le.eval_set_hash <> public.sf_eval_set_hash(v.id) then false
      else le.pass_rate >= (v.manifest #>> '{release_criteria,min_eval_pass_rate}')::numeric
    end)
    and (not coalesce((v.manifest #>> '{release_criteria,require_approval}')::boolean, true)
         or (la.decision = 'approve' and la.manifest_hash = v.manifest_hash))
    and v.status in ('draft','in_review','approved')
  ) as publishable
from public.sf_skill_versions v
join public.sf_skills s on s.id = v.skill_id
left join latest_eval le on le.version_id = v.id
left join latest_approval la on la.version_id = v.id
left join case_counts cc on cc.version_id = v.id;
grant select on public.sf_version_release_state to authenticated;

-- ───────────────────────────── review / publish / retire ─────────────────────────────
create or replace function public.sf_review_version(p_version uuid, p_decision text, p_note text default '')
returns jsonb language plpgsql security definer set search_path = public as $$
declare v record; v_role text;
begin
  select v2.*, s.workspace_id into v from public.sf_skill_versions v2 join public.sf_skills s on s.id = v2.skill_id where v2.id = p_version;
  if v is null then raise exception 'version not found' using errcode = 'no_data_found'; end if;
  v_role := public.sf_role(v.workspace_id);
  if v_role not in ('reviewer','admin') then raise exception 'reviewers or admins only' using errcode = 'insufficient_privilege'; end if;
  if v.status <> 'in_review' then raise exception 'version is % — only versions in review can be approved or rejected', v.status using errcode = 'check_violation'; end if;
  if p_decision not in ('approve','reject') then raise exception 'decision must be approve or reject' using errcode = 'check_violation'; end if;
  if v.created_by = auth.uid() and v_role <> 'admin' then
    raise exception 'a reviewer cannot approve a version they authored (an admin can)' using errcode = 'insufficient_privilege';
  end if;
  perform set_config('sf.rpc', '1', true);
  insert into public.sf_approvals (version_id, manifest_hash, decision, note, reviewer_id)
  values (p_version, v.manifest_hash, p_decision, coalesce(p_note, ''), auth.uid());
  update public.sf_skill_versions set status = case when p_decision = 'approve' then 'approved' else 'draft' end where id = p_version;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v.workspace_id, auth.uid(), 'user', 'version.' || p_decision, 'skill_version', p_version::text,
          jsonb_build_object('manifest_hash', v.manifest_hash, 'note', coalesce(p_note, ''), 'skill_id', v.skill_id, 'version', v.version));
  return jsonb_build_object('ok', true, 'status', case when p_decision = 'approve' then 'approved' else 'draft' end);
end $$;
grant execute on function public.sf_review_version(uuid, text, text) to authenticated;

-- Publishing is gated here, not in the UI: the approval must match the current manifest hash and the
-- evaluation gate must be met against the current evaluation set.
create or replace function public.sf_publish_version(p_version uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v record; rs record; v_role text;
begin
  select v2.*, s.workspace_id into v from public.sf_skill_versions v2 join public.sf_skills s on s.id = v2.skill_id where v2.id = p_version;
  if v is null then raise exception 'version not found' using errcode = 'no_data_found'; end if;
  v_role := public.sf_role(v.workspace_id);
  if v_role not in ('author','admin') then raise exception 'authors or admins only' using errcode = 'insufficient_privilege'; end if;
  select * into rs from public.sf_version_release_state where version_id = p_version;
  if v.status not in ('draft','in_review','approved') then
    raise exception 'version is % and cannot be published', v.status using errcode = 'check_violation';
  end if;
  if rs.require_approval and not coalesce(rs.approval_valid, false) then
    if coalesce(rs.approval_stale, false) then
      raise exception 'approval is stale: the manifest changed after it was approved — request review again' using errcode = 'check_violation';
    end if;
    raise exception 'no valid approval for this version (release criteria require one)' using errcode = 'check_violation';
  end if;
  if not coalesce(rs.eval_gate_met, false) then
    if rs.eval_case_count = 0 then
      raise exception 'evaluation gate not met: no evaluation cases (minimum pass rate %)', rs.min_eval_pass_rate using errcode = 'check_violation';
    elsif not coalesce(rs.eval_current, false) then
      raise exception 'evaluation gate not met: no evaluation run on the current case set — run the evaluation again' using errcode = 'check_violation';
    end if;
    raise exception 'evaluation gate not met: latest pass rate % is below the required %', rs.latest_eval_pass_rate, rs.min_eval_pass_rate using errcode = 'check_violation';
  end if;
  perform set_config('sf.rpc', '1', true);
  update public.sf_skill_versions set status = 'superseded' where skill_id = v.skill_id and status = 'published' and id <> p_version;
  update public.sf_skill_versions set status = 'published', published_at = now() where id = p_version;
  update public.sf_skills set status = 'published', latest_version_id = p_version where id = v.skill_id;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v.workspace_id, auth.uid(), 'user', 'version.publish', 'skill_version', p_version::text,
          jsonb_build_object('skill_id', v.skill_id, 'version', v.version, 'manifest_hash', v.manifest_hash,
                             'eval_pass_rate', rs.latest_eval_pass_rate, 'approval_id', rs.latest_approval_id));
  return jsonb_build_object('ok', true, 'version', v.version);
end $$;
grant execute on function public.sf_publish_version(uuid) to authenticated;

create or replace function public.sf_retire_version(p_version uuid, p_note text default '')
returns jsonb language plpgsql security definer set search_path = public as $$
declare v record; v_role text; v_remaining int;
begin
  select v2.*, s.workspace_id into v from public.sf_skill_versions v2 join public.sf_skills s on s.id = v2.skill_id where v2.id = p_version;
  if v is null then raise exception 'version not found' using errcode = 'no_data_found'; end if;
  v_role := public.sf_role(v.workspace_id);
  if v_role not in ('author','admin') then raise exception 'authors or admins only' using errcode = 'insufficient_privilege'; end if;
  if v.status <> 'published' then raise exception 'only a published version can be retired (it is %)', v.status using errcode = 'check_violation'; end if;
  perform set_config('sf.rpc', '1', true);
  update public.sf_skill_versions set status = 'retired' where id = p_version;
  select count(*) into v_remaining from public.sf_skill_versions where skill_id = v.skill_id and status = 'published';
  update public.sf_skills set status = case when v_remaining > 0 then 'published' else 'retired' end,
         latest_version_id = case when v_remaining > 0 then latest_version_id else null end
   where id = v.skill_id;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v.workspace_id, auth.uid(), 'user', 'version.retire', 'skill_version', p_version::text,
          jsonb_build_object('skill_id', v.skill_id, 'version', v.version, 'note', coalesce(p_note, '')));
  return jsonb_build_object('ok', true);
end $$;
grant execute on function public.sf_retire_version(uuid, text) to authenticated;

-- ───────────────────────────── runs (UI path) ─────────────────────────────
-- Creates the run row after the server-side checks that must be atomic: concurrency and monthly budget.
create or replace function public.sf_run_insert(p_version uuid, p_source text, p_inputs_ref jsonb, p_idempotency_key text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v record; pol record; v_running int; v_spend numeric; v_existing uuid; v_id uuid; v_role text;
begin
  select v2.*, s.workspace_id into v from public.sf_skill_versions v2 join public.sf_skills s on s.id = v2.skill_id where v2.id = p_version;
  if v is null then raise exception 'version not found' using errcode = 'no_data_found'; end if;
  v_role := public.sf_role(v.workspace_id);
  if v_role is null then raise exception 'not a member of this workspace' using errcode = 'insufficient_privilege'; end if;
  if v.status <> 'published' and v_role = 'consumer' then
    raise exception 'consumers can only run published versions (this one is %)', v.status using errcode = 'insufficient_privilege';
  end if;
  if v.status in ('retired','superseded') then
    raise exception 'version is % and cannot be run', v.status using errcode = 'check_violation';
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
  insert into public.sf_runs (workspace_id, version_id, invoked_by, source, status, idempotency_key, inputs_ref)
  values (v.workspace_id, p_version, auth.uid(), p_source, 'queued', p_idempotency_key, coalesce(p_inputs_ref, '[]'::jsonb))
  returning id into v_id;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v.workspace_id, auth.uid(), 'user', 'run.create', 'run', v_id::text, jsonb_build_object('version_id', p_version, 'source', p_source));
  return jsonb_build_object('run_id', v_id, 'existing', false, 'workspace_id', v.workspace_id);
end $$;
grant execute on function public.sf_run_insert(uuid, text, jsonb, text) to authenticated;

-- ───────────────────────────── API keys (consumer API; anon role + key hash) ─────────────────────────────
create or replace function public.sf_resolve_api_key(p_key_hash text)
returns table (api_key_id uuid, workspace_id uuid)
language plpgsql security definer set search_path = public as $$
begin
  return query
    update public.sf_api_keys k set last_used_at = now()
    where k.key_hash = p_key_hash and k.revoked_at is null
    returning k.id, k.workspace_id;
end $$;
grant execute on function public.sf_resolve_api_key(text) to anon, authenticated;

create or replace function public.sf_api_skills(p_key_hash text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; out jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select coalesce(jsonb_agg(jsonb_build_object(
           'slug', s.slug, 'name', s.name, 'purpose', s.purpose, 'intended_users', s.intended_users, 'usage_guidance', s.usage_guidance,
           'version', v.version, 'version_id', v.id, 'published_at', v.published_at, 'manifest_hash', v.manifest_hash,
           'inputs', v.manifest->'inputs', 'outputs', v.manifest->'outputs') order by s.slug), '[]'::jsonb)
  into out
  from public.sf_skills s join public.sf_skill_versions v on v.id = s.latest_version_id
  where s.workspace_id = v_ws and s.status = 'published' and v.status = 'published';
  return out;
end $$;
grant execute on function public.sf_api_skills(text) to anon, authenticated;

create or replace function public.sf_api_skill(p_key_hash text, p_slug text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; out jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select jsonb_build_object(
           'slug', s.slug, 'name', s.name, 'purpose', s.purpose, 'intended_users', s.intended_users, 'usage_guidance', s.usage_guidance,
           'skill_id', s.id, 'workspace_id', s.workspace_id, 'version', v.version, 'version_id', v.id, 'published_at', v.published_at,
           'manifest_hash', v.manifest_hash, 'manifest', v.manifest, 'source', v.source,
           'files', (select coalesce(jsonb_agg(jsonb_build_object('path', f.path, 'content', f.content) order by f.path), '[]'::jsonb)
                     from public.sf_files f where f.version_id = v.id),
           'policy', (select to_jsonb(p) from public.sf_policies p where p.workspace_id = s.workspace_id))
  into out
  from public.sf_skills s join public.sf_skill_versions v on v.id = s.latest_version_id
  where s.workspace_id = v_ws and s.slug = p_slug and s.status = 'published' and v.status = 'published';
  return out;  -- null when no published version
end $$;
grant execute on function public.sf_api_skill(text, text) to anon, authenticated;

-- Creates a queued run for the published version of a skill (API path). Same concurrency/budget/idempotency rules as the UI.
create or replace function public.sf_record_run(p_key_hash text, p_slug text, p_inputs_ref jsonb, p_idempotency_key text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; v record; pol record; v_running int; v_spend numeric; v_existing uuid; v_id uuid;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select v2.*, s.workspace_id into v from public.sf_skills s join public.sf_skill_versions v2 on v2.id = s.latest_version_id
   where s.workspace_id = v_ws and s.slug = p_slug and s.status = 'published' and v2.status = 'published';
  if v is null then raise exception 'no published version' using errcode = 'no_data_found'; end if;
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
  insert into public.sf_runs (workspace_id, version_id, api_key_id, source, status, idempotency_key, inputs_ref)
  values (v_ws, v.id, v_key, 'api', 'queued', p_idempotency_key, coalesce(p_inputs_ref, '[]'::jsonb)) returning id into v_id;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v_ws, v_key, 'api_key', 'run.create', 'run', v_id::text, jsonb_build_object('version_id', v.id, 'source', 'api', 'slug', p_slug));
  return jsonb_build_object('run_id', v_id, 'existing', false, 'version_id', v.id, 'workspace_id', v_ws, 'manifest', v.manifest, 'source', v.source, 'version', v.version);
end $$;
grant execute on function public.sf_record_run(text, text, jsonb, text) to anon, authenticated;

-- Writes the result of an API-path run. Only the columns listed are patchable.
create or replace function public.sf_api_run_update(p_key_hash text, p_run uuid, p_patch jsonb)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  update public.sf_runs r set
    status           = coalesce(p_patch->>'status', r.status),
    run_json         = coalesce(p_patch->'run_json', r.run_json),
    outputs          = coalesce(p_patch->'outputs', r.outputs),
    logs             = coalesce(p_patch->>'logs', r.logs),
    provider         = coalesce(p_patch->>'provider', r.provider),
    model            = coalesce(p_patch->>'model', r.model),
    usage            = coalesce(p_patch->'usage', r.usage),
    cost_usd         = coalesce((p_patch->>'cost_usd')::numeric, r.cost_usd),
    cost_is_estimate = coalesce((p_patch->>'cost_is_estimate')::boolean, r.cost_is_estimate),
    started_at       = coalesce((p_patch->>'started_at')::timestamptz, r.started_at),
    finished_at      = coalesce((p_patch->>'finished_at')::timestamptz, r.finished_at),
    duration_ms      = coalesce((p_patch->>'duration_ms')::int, r.duration_ms),
    error            = coalesce(p_patch->>'error', r.error)
  where r.id = p_run and r.workspace_id = v_ws;
  if not found then raise exception 'run not found' using errcode = 'no_data_found'; end if;
  return jsonb_build_object('ok', true);
end $$;
grant execute on function public.sf_api_run_update(text, uuid, jsonb) to anon, authenticated;

create or replace function public.sf_api_run_get(p_key_hash text, p_run uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; out jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select to_jsonb(r) - 'logs' || jsonb_build_object('skill_slug', s.slug, 'version', v.version) into out
  from public.sf_runs r join public.sf_skill_versions v on v.id = r.version_id join public.sf_skills s on s.id = v.skill_id
  where r.id = p_run and r.workspace_id = v_ws;
  return out;
end $$;
grant execute on function public.sf_api_run_get(text, uuid) to anon, authenticated;
