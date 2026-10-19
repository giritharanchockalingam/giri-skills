-- 0005_sf_mcp.sql — read paths the MCP server needs for an API-key caller (anon role + key hash, like 0002's sf_api_*):
--   sf_api_catalog(key)            published skills of the key's workspace, with the library skill each was imported from
--   sf_api_talent(key, kind, slug) the PUBLISHED spec of a workspace role or team (pool), so a tailored role scopes its server
-- VOLATILE (not STABLE): PostgREST runs STABLE functions in a read-only transaction, and the key check records
-- last_used_at. SECURITY DEFINER with a fixed search_path; re-verifies the key on every call. Idempotent; sf_ prefix only.
-- rollback: (manual, in this order — drops everything this migration created; no data)
--   drop function if exists public.sf_api_talent(text, text, text);
--   drop function if exists public.sf_api_catalog(text);

create or replace function public.sf_api_catalog(p_key_hash text)
returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; out jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select coalesce(jsonb_agg(jsonb_build_object(
           'slug', s.slug, 'name', s.name, 'purpose', s.purpose, 'version', v.version, 'version_id', v.id,
           'repo_skill', case when v.source->>'kind' = 'repo' then v.source->>'repo_skill' end,
           'inputs', v.manifest->'inputs', 'outputs', v.manifest->'outputs') order by s.slug), '[]'::jsonb)
  into out
  from public.sf_skills s join public.sf_skill_versions v on v.id = s.latest_version_id
  where s.workspace_id = v_ws and s.status = 'published' and v.status = 'published';
  return out;
end $$;
grant execute on function public.sf_api_catalog(text) to anon, authenticated;

create or replace function public.sf_api_talent(p_key_hash text, p_kind text, p_slug text)
returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; out jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  if p_kind not in ('role', 'pool') then raise exception 'kind must be role or pool' using errcode = 'invalid_parameter_value'; end if;
  select jsonb_build_object('slug', t.slug, 'name', t.name, 'version', tv.version, 'spec', tv.spec)
  into out
  from public.sf_talent t join public.sf_talent_versions tv on tv.talent_id = t.id and tv.status = 'published'
  where t.workspace_id = v_ws and t.kind = p_kind and t.slug = p_slug;
  return out;  -- null when the role/team does not exist here or has no published version
end $$;
grant execute on function public.sf_api_talent(text, text, text) to anon, authenticated;
