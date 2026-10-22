-- 0024: composed pipelines (docs/DELIVERY-PIPELINES.md → When no template fits). A run started from a composed pipeline
-- carries the pipeline's full JSON in `pipeline_spec`; the executor reads it back from the run (GET /api/delivery-runs/{id})
-- when no template of that name exists in pipelines/. Additive only: one column, and sf_delivery_run_start learns to store
-- it (p_payload->'pipeline_spec'); sf_api_catalog_repo lets an API key (MCP `compose`) read a catalog repository's stack.
-- rollback: (manual — in this order; sf_delivery_run_start returns to its 0022 body when 0022 is re-applied; the column is
-- nullable and unused by 0022, so it may stay)
--   drop function if exists public.sf_api_catalog_repo(text, text);
alter table public.sf_delivery_runs add column if not exists pipeline_spec jsonb;

create or replace function public.sf_delivery_run_start(p_payload jsonb, p_key_hash text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; v_user uuid; v_acc jsonb; v_id uuid; v_pipeline text; v_spec jsonb;
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
  -- a composed pipeline travels on the run; it must be an object named like the run's pipeline
  v_spec := p_payload->'pipeline_spec';
  if v_spec is not null and (jsonb_typeof(v_spec) <> 'object' or v_spec->>'name' is distinct from v_pipeline) then
    raise exception 'pipeline_spec must be the composed pipeline named %', v_pipeline using errcode = 'check_violation';
  end if;
  v_acc := public.sf_delivery_access(v_ws, v_pipeline, v_user, v_key);
  if not (v_acc->>'allowed')::boolean then
    insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
    values (v_ws, coalesce(v_user, v_key), case when v_user is null then 'api_key' else 'user' end, 'delivery.denied', 'pipeline', v_pipeline, jsonb_build_object('reason', v_acc->>'reason'));
    return jsonb_build_object('error', v_acc->>'reason', 'message', 'This pipeline is not open to any role assigned to you. Ask an administrator for access.');
  end if;
  insert into public.sf_delivery_runs (workspace_id, pipeline, pipeline_version, mode, repo, ref, request, status, stage, stages, executor, created_by, api_key_id, pipeline_spec)
  values (v_ws, v_pipeline, coalesce(p_payload->>'pipeline_version', ''), p_payload->>'mode', p_payload->>'repo', coalesce(p_payload->>'ref', ''), p_payload->>'request',
          'queued', p_payload->'stages'->0->>'id', coalesce(p_payload->'stages', '[]'::jsonb), p_payload->>'executor', v_user, v_key, v_spec)
  returning id into v_id;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v_ws, coalesce(v_user, v_key), case when v_user is null then 'api_key' else 'user' end, 'delivery.start', 'delivery_run', v_id::text,
          jsonb_build_object('pipeline', v_pipeline, 'repo', p_payload->>'repo', 'ref', coalesce(p_payload->>'ref', ''), 'executor', p_payload->>'executor', 'composed', v_spec is not null)
          || case when v_acc ? 'role_slug' then jsonb_build_object('role', v_acc->>'role_slug') else '{}'::jsonb end);
  return (select to_jsonb(r) from public.sf_delivery_runs r where r.id = v_id);
end $$;
grant execute on function public.sf_delivery_run_start(jsonb, text) to anon, authenticated;

-- API-key read of one catalog repository (key = owner/name) in the key's workspace: its stack signals for `compose`.
create or replace function public.sf_api_catalog_repo(p_key_hash text, p_repo text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; out jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select jsonb_build_object('id', e.id, 'key', e.key, 'title', e.title, 'url', e.url, 'archived', e.archived, 'stack', coalesce(e.properties->'stack', '[]'::jsonb))
    into out from public.sf_catalog_entities e where e.workspace_id = v_ws and e.kind = 'repository' and e.key = p_repo;
  return out;
end $$;
grant execute on function public.sf_api_catalog_repo(text, text) to anon, authenticated;
