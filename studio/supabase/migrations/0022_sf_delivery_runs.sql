-- 0022: delivery runs — the portal as control plane for docs/DELIVERY-PIPELINES.md.
-- A run is one request through one pipeline template (pipelines/<name>.json) on one repository. The executor
-- (GitHub Actions `delivery.yml`, or scripts/deliver.py from an IDE) does the work and posts one stage record at a
-- time through sf_delivery_run_set_stage; people approve stages in the portal (sf_delivery_approvals); admins say who
-- may start which pipeline (sf_pipeline_access: no rows for a pipeline = any member may start it).
-- Evidence is immutable once a run succeeded (trigger). Approvals are append-only. sf_ prefix only; idempotent.
-- rollback: (manual — in this order)
--   drop function if exists public.sf_api_delivery_get(text, uuid);
--   drop function if exists public.sf_delivery_run_set_stage(uuid, jsonb, jsonb, text);
--   drop function if exists public.sf_delivery_run_start(jsonb, text);
--   drop function if exists public.sf_delivery_access(uuid, text, uuid, uuid);
--   drop function if exists public.sf_delivery_run_guard() cascade;
--   drop table if exists public.sf_delivery_approvals cascade;
--   drop table if exists public.sf_pipeline_access cascade;
--   drop table if exists public.sf_delivery_runs cascade;

-- ───────────────────────────── tables ─────────────────────────────
create table if not exists public.sf_delivery_runs (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references public.sf_workspaces(id) on delete cascade,
  pipeline         text not null check (pipeline ~ '^[a-z0-9][a-z0-9-]{0,78}$'),
  pipeline_version text not null default '',
  mode             text not null check (mode in ('brownfield', 'greenfield')),
  repo             text not null check (length(repo) between 1 and 300),
  ref              text not null default '',
  request          text not null check (length(request) between 1 and 20000),
  status           text not null default 'queued' check (status in ('queued', 'running', 'awaiting_approval', 'blocked', 'failed', 'succeeded')),
  stage            text,                                                        -- id of the current stage
  stages           jsonb not null default '[]'::jsonb check (jsonb_typeof(stages) = 'array'),
  -- [{id, adlc_stage, role, status, gate:{kind, verdict, detail}, evidence:[{path, sha256, bytes}], started_at, finished_at}]
  stack_profile    jsonb,                                                       -- scripts/stack_profile.py output, posted by the executor
  pr               jsonb,                                                       -- {number, url, head_sha}
  executor         text not null check (executor in ('github-actions', 'ide', 'local')),
  executor_ref     text,                                                        -- workflow run url / machine label / notice
  created_by       uuid references auth.users(id) on delete set null,
  api_key_id       uuid references public.sf_api_keys(id) on delete set null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  error            text,
  check (num_nonnulls(created_by, api_key_id) >= 1)
);
create index if not exists sf_delivery_runs_ws_idx on public.sf_delivery_runs (workspace_id, created_at desc);
create index if not exists sf_delivery_runs_status_idx on public.sf_delivery_runs (workspace_id, status);
create index if not exists sf_delivery_runs_repo_idx on public.sf_delivery_runs (workspace_id, repo);

create table if not exists public.sf_delivery_approvals (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid not null references public.sf_delivery_runs(id) on delete cascade,
  stage_id      text not null,
  role          text not null,                                                  -- the role slug that owns the stage
  approved_by   uuid not null references auth.users(id),
  note          text not null default '',
  created_at    timestamptz not null default now()
);
create index if not exists sf_delivery_approvals_run_idx on public.sf_delivery_approvals (run_id, created_at);

create table if not exists public.sf_pipeline_access (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  pipeline      text not null check (pipeline ~ '^[a-z0-9][a-z0-9-]{0,78}$'),
  role_slug     text not null check (role_slug ~ '^[a-z0-9][a-z0-9-]{0,78}$'),
  created_by    uuid references auth.users(id),
  created_at    timestamptz not null default now(),
  unique (workspace_id, pipeline, role_slug)
);
create index if not exists sf_pipeline_access_ws_idx on public.sf_pipeline_access (workspace_id, pipeline);

-- ───────────────────────────── triggers ─────────────────────────────
-- Evidence is a record: once a run succeeded, its stages (evidence, gates), PR and status never change.
create or replace function public.sf_delivery_run_guard() returns trigger language plpgsql set search_path = public as $$
begin
  if old.status = 'succeeded' and (new.stages is distinct from old.stages or new.pr is distinct from old.pr or new.status is distinct from old.status
                                   or new.stack_profile is distinct from old.stack_profile) then
    raise exception 'delivery run % succeeded: its evidence is immutable', old.id using errcode = 'check_violation';
  end if;
  if new.workspace_id <> old.workspace_id or new.pipeline <> old.pipeline or new.repo <> old.repo or new.created_at <> old.created_at then
    raise exception 'delivery run identity cannot change' using errcode = 'check_violation';
  end if;
  new.updated_at := now();
  return new;
end $$;
do $$ begin if not exists (select 1 from pg_trigger where tgname = 'sf_delivery_runs_guard') then
  create trigger sf_delivery_runs_guard before update on public.sf_delivery_runs for each row execute function public.sf_delivery_run_guard(); end if; end $$;
do $$ begin if not exists (select 1 from pg_trigger where tgname = 'sf_delivery_approvals_append_only') then
  create trigger sf_delivery_approvals_append_only before update or delete on public.sf_delivery_approvals for each row execute function public.sf_reject_change(); end if; end $$;

-- ───────────────────────────── RLS ─────────────────────────────
alter table public.sf_delivery_runs enable row level security;
alter table public.sf_delivery_approvals enable row level security;
alter table public.sf_pipeline_access enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_delivery_runs' and policyname='sf_delivery_runs_select') then execute $p$
    create policy sf_delivery_runs_select on public.sf_delivery_runs for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  -- inserts go through sf_delivery_run_start (access rule + audit); updates through sf_delivery_run_set_stage. No direct write policies.
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_delivery_approvals' and policyname='sf_delivery_approvals_select') then execute $p$
    create policy sf_delivery_approvals_select on public.sf_delivery_approvals for select to authenticated
    using (exists (select 1 from public.sf_delivery_runs r where r.id = run_id and public.sf_is_member(r.workspace_id))) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_delivery_approvals' and policyname='sf_delivery_approvals_insert') then execute $p$
    create policy sf_delivery_approvals_insert on public.sf_delivery_approvals for insert to authenticated
    with check (approved_by = auth.uid() and exists (select 1 from public.sf_delivery_runs r where r.id = run_id and public.sf_is_member(r.workspace_id))) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_pipeline_access' and policyname='sf_pipeline_access_select') then execute $p$
    create policy sf_pipeline_access_select on public.sf_pipeline_access for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_pipeline_access' and policyname='sf_pipeline_access_insert') then execute $p$
    create policy sf_pipeline_access_insert on public.sf_pipeline_access for insert to authenticated
    with check (public.sf_has_role(workspace_id, array['admin']) and created_by = auth.uid()) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_pipeline_access' and policyname='sf_pipeline_access_delete') then execute $p$
    create policy sf_pipeline_access_delete on public.sf_pipeline_access for delete to authenticated using (public.sf_has_role(workspace_id, array['admin'])) $p$; end if;
end $$;
grant select on public.sf_delivery_runs to authenticated;
grant select, insert on public.sf_delivery_approvals to authenticated;
grant select, insert, delete on public.sf_pipeline_access to authenticated;

-- ───────────────────────────── access rule ─────────────────────────────
-- Who may start a pipeline. Admins always; a pipeline with no sf_pipeline_access rows is open to every member and
-- every key of the workspace; otherwise the holder must be assigned (sf_role_assignments) to a role whose slug is listed.
-- Internal (no grant): callers pass a holder.
create or replace function public.sf_delivery_access(p_ws uuid, p_pipeline text, p_user uuid, p_key uuid)
returns jsonb language plpgsql stable security definer set search_path = public as $$
declare v_role text; v_rows int; g record;
begin
  if p_user is not null then
    select m.role into v_role from public.sf_memberships m where m.workspace_id = p_ws and m.user_id = p_user;
    if v_role is null then return jsonb_build_object('allowed', false, 'reason', 'not_member'); end if;
    if v_role = 'admin' then return jsonb_build_object('allowed', true, 'reason', 'admin'); end if;
  elsif p_key is null or not exists (select 1 from public.sf_api_keys k where k.id = p_key and k.workspace_id = p_ws and k.revoked_at is null) then
    return jsonb_build_object('allowed', false, 'reason', 'not_member');
  end if;
  select count(*) into v_rows from public.sf_pipeline_access a where a.workspace_id = p_ws and a.pipeline = p_pipeline;
  if v_rows = 0 then return jsonb_build_object('allowed', true, 'reason', 'open'); end if;
  select t.slug into g
    from public.sf_pipeline_access a
    join public.sf_talent t on t.workspace_id = a.workspace_id and t.kind = 'role' and t.slug = a.role_slug
    join public.sf_role_assignments ra on ra.talent_id = t.id
   where a.workspace_id = p_ws and a.pipeline = p_pipeline
     and ((p_user is not null and ra.user_id = p_user) or (p_key is not null and ra.api_key_id = p_key))
   order by t.slug limit 1;
  if not found then return jsonb_build_object('allowed', false, 'reason', 'not_in_role'); end if;
  return jsonb_build_object('allowed', true, 'reason', 'role', 'role_slug', g.slug);
end $$;
revoke all on function public.sf_delivery_access(uuid, text, uuid, uuid) from public, anon, authenticated;

-- ───────────────────────────── start a run ─────────────────────────────
-- p_payload: {workspace_id (session callers only), pipeline, pipeline_version, mode, repo, ref, request, executor, stages}
-- Session callers (p_key_hash null) act as auth.uid(); API-key callers act as the key's workspace. A refusal is
-- audited (delivery.denied) and answered as {"error": "..."} so the audit row commits.
create or replace function public.sf_delivery_run_start(p_payload jsonb, p_key_hash text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; v_user uuid; v_acc jsonb; v_id uuid; v_pipeline text;
begin
  v_pipeline := p_payload->>'pipeline';
  if p_key_hash is not null then
    select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
    if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  else
    v_user := auth.uid();
    v_ws := (p_payload->>'workspace_id')::uuid;
    if v_user is null or v_ws is null or not public.sf_is_member(v_ws) then raise exception 'not a member of this workspace' using errcode = 'insufficient_privilege'; end if;
  end if;
  if v_pipeline is null or v_pipeline !~ '^[a-z0-9][a-z0-9-]{0,78}$' then raise exception 'pipeline is required' using errcode = 'check_violation'; end if;
  v_acc := public.sf_delivery_access(v_ws, v_pipeline, v_user, v_key);
  if not (v_acc->>'allowed')::boolean then
    insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
    values (v_ws, coalesce(v_user, v_key), case when v_user is null then 'api_key' else 'user' end, 'delivery.denied', 'pipeline', v_pipeline, jsonb_build_object('reason', v_acc->>'reason'));
    return jsonb_build_object('error', v_acc->>'reason', 'message', 'This pipeline is not open to any role assigned to you. Ask an administrator for access.');
  end if;
  insert into public.sf_delivery_runs (workspace_id, pipeline, pipeline_version, mode, repo, ref, request, status, stage, stages, executor, created_by, api_key_id)
  values (v_ws, v_pipeline, coalesce(p_payload->>'pipeline_version', ''), p_payload->>'mode', p_payload->>'repo', coalesce(p_payload->>'ref', ''), p_payload->>'request',
          'queued', p_payload->'stages'->0->>'id', coalesce(p_payload->'stages', '[]'::jsonb), p_payload->>'executor', v_user, v_key)
  returning id into v_id;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v_ws, coalesce(v_user, v_key), case when v_user is null then 'api_key' else 'user' end, 'delivery.start', 'delivery_run', v_id::text,
          jsonb_build_object('pipeline', v_pipeline, 'repo', p_payload->>'repo', 'ref', coalesce(p_payload->>'ref', ''), 'executor', p_payload->>'executor')
          || case when v_acc ? 'role_slug' then jsonb_build_object('role', v_acc->>'role_slug') else '{}'::jsonb end);
  return (select to_jsonb(r) from public.sf_delivery_runs r where r.id = v_id);
end $$;
grant execute on function public.sf_delivery_run_start(jsonb, text) to anon, authenticated;

-- ───────────────────────────── executor callback ─────────────────────────────
-- Upserts one stage record (merged by id, order kept) and applies the run-level patch the server computed
-- ({status, stage, stack_profile, pr, executor_ref, error}). With p_stage null only the patch is applied (executor notices). Session callers must be members; API-key callers must
-- hold a key of the run's workspace. Refused once the run succeeded (evidence is immutable). Audited (delivery.stage).
create or replace function public.sf_delivery_run_set_stage(p_run uuid, p_stage jsonb, p_patch jsonb default '{}'::jsonb, p_key_hash text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare r record; v_ws uuid; v_key uuid; v_user uuid; v_new jsonb := '[]'::jsonb; v_found boolean := false; el jsonb;
begin
  if p_stage is not null and (jsonb_typeof(p_stage) <> 'object' or coalesce(p_stage->>'id', '') = '') then raise exception 'stage.id is required' using errcode = 'check_violation'; end if;
  select * into r from public.sf_delivery_runs where id = p_run;
  if r is null then raise exception 'run not found' using errcode = 'no_data_found'; end if;
  if p_key_hash is not null then
    select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
    if v_ws is null or v_ws <> r.workspace_id then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  else
    v_user := auth.uid();
    if v_user is null or not public.sf_is_member(r.workspace_id) then raise exception 'not a member of this workspace' using errcode = 'insufficient_privilege'; end if;
  end if;
  if r.status = 'succeeded' then raise exception 'delivery run % succeeded: its evidence is immutable', p_run using errcode = 'check_violation'; end if;
  v_new := coalesce(r.stages, '[]'::jsonb);
  if p_stage is not null then
    v_new := '[]'::jsonb;
    for el in select * from jsonb_array_elements(coalesce(r.stages, '[]'::jsonb)) loop
      if el->>'id' = p_stage->>'id' then v_new := v_new || jsonb_build_array(el || p_stage); v_found := true;
      else v_new := v_new || jsonb_build_array(el); end if;
    end loop;
    if not v_found then v_new := v_new || jsonb_build_array(p_stage); end if;
  end if;
  update public.sf_delivery_runs x set
    stages        = v_new,
    stage         = coalesce(p_patch->>'stage', p_stage->>'id', x.stage),
    status        = coalesce(p_patch->>'status', x.status),
    stack_profile = coalesce(p_patch->'stack_profile', x.stack_profile),
    pr            = coalesce(p_patch->'pr', x.pr),
    executor_ref  = coalesce(p_patch->>'executor_ref', x.executor_ref),
    error         = case when p_patch ? 'error' then p_patch->>'error' else x.error end
  where x.id = p_run;
  if p_stage is not null then
    insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
    values (r.workspace_id, coalesce(v_user, v_key), case when v_user is null then 'api_key' else 'user' end, 'delivery.stage', 'delivery_run', p_run::text,
            jsonb_build_object('stage', p_stage->>'id', 'stage_status', p_stage->>'status', 'gate', p_stage->'gate'->>'verdict', 'status', coalesce(p_patch->>'status', r.status)));
  end if;
  return (select to_jsonb(x) from public.sf_delivery_runs x where x.id = p_run);
end $$;
grant execute on function public.sf_delivery_run_set_stage(uuid, jsonb, jsonb, text) to anon, authenticated;

-- ───────────────────────────── read (API key) ─────────────────────────────
create or replace function public.sf_api_delivery_get(p_key_hash text, p_run uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; out jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select to_jsonb(r) || jsonb_build_object('approvals', coalesce((select jsonb_agg(to_jsonb(a) order by a.created_at) from public.sf_delivery_approvals a where a.run_id = r.id), '[]'::jsonb))
    into out from public.sf_delivery_runs r where r.id = p_run and r.workspace_id = v_ws;
  return out;
end $$;
grant execute on function public.sf_api_delivery_get(text, uuid) to anon, authenticated;
