-- 0020: access requests and what an API key may run (docs/ACCESS-BY-ROLE.md, PR 3).
-- A member asks for a published job role (usually from a skill they cannot run); any admin approves or declines in
-- the Inbox, never their own request; approval assigns the role. Requests are created and decided only through the
-- functions below (no direct writes). sf_api_catalog / sf_api_skills now say, per skill, whether the calling key may
-- run it (same rule, sf_run_access), so MCP lists only runnable tools. sf_ prefix only; idempotent.
-- rollback: (manual — in this order; then re-run sf_api_catalog from 0005_sf_mcp.sql and sf_api_skills from 0002_sf_functions.sql)
--   drop function if exists public.sf_access_decide(uuid, boolean, text);
--   drop function if exists public.sf_access_request(uuid, uuid, text, text);
--   drop table if exists public.sf_access_requests cascade;

create table if not exists public.sf_access_requests (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  talent_id     uuid not null references public.sf_talent(id) on delete cascade,
  skill         text check (skill is null or length(skill) <= 200),            -- the skill that prompted it (library id or slug)
  note          text not null default '' check (length(note) <= 1000),
  status        text not null default 'pending' check (status in ('pending', 'approved', 'declined')),
  requested_by  uuid not null references auth.users(id) on delete cascade,
  decided_by    uuid references auth.users(id),
  decided_at    timestamptz,
  decision_note text check (decision_note is null or length(decision_note) <= 1000),
  created_at    timestamptz not null default now()
);
create unique index if not exists sf_access_requests_pending_uq on public.sf_access_requests (talent_id, requested_by) where status = 'pending';
create index if not exists sf_access_requests_ws_idx on public.sf_access_requests (workspace_id, created_at desc);

alter table public.sf_access_requests enable row level security;
-- admins see every request in the workspace; everyone else sees their own
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_access_requests' and policyname='sf_access_requests_select') then execute $p$
  create policy sf_access_requests_select on public.sf_access_requests for select to authenticated
  using (public.sf_has_role(workspace_id, array['admin']) or (requested_by = auth.uid() and public.sf_is_member(workspace_id))) $p$; end if; end $$;
grant select on public.sf_access_requests to authenticated;   -- writes only through the functions below

create or replace function public.sf_access_request(p_workspace uuid, p_talent uuid, p_skill text, p_note text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_id uuid;
begin
  if auth.uid() is null or not public.sf_is_member(p_workspace) then raise exception 'not a member of this workspace' using errcode = 'insufficient_privilege'; end if;
  if not exists (select 1 from public.sf_talent t join public.sf_talent_versions tv on tv.talent_id = t.id and tv.status = 'published'
                 where t.id = p_talent and t.workspace_id = p_workspace and t.kind = 'role') then
    raise exception 'job role not found or not published' using errcode = 'check_violation'; end if;
  if exists (select 1 from public.sf_role_assignments where talent_id = p_talent and user_id = auth.uid()) then
    raise exception 'you already hold this job role' using errcode = 'check_violation'; end if;
  insert into public.sf_access_requests (workspace_id, talent_id, skill, note, requested_by)
  values (p_workspace, p_talent, nullif(left(coalesce(p_skill, ''), 200), ''), left(coalesce(p_note, ''), 1000), auth.uid())
  on conflict (talent_id, requested_by) where status = 'pending' do nothing
  returning id into v_id;
  if v_id is null then
    select id into v_id from public.sf_access_requests where talent_id = p_talent and requested_by = auth.uid() and status = 'pending';
    return jsonb_build_object('id', v_id, 'existing', true);
  end if;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (p_workspace, auth.uid(), 'user', 'access.request', 'access_request', v_id::text, jsonb_build_object('talent_id', p_talent, 'skill', p_skill));
  return jsonb_build_object('id', v_id, 'existing', false);
end $$;
revoke all on function public.sf_access_request(uuid, uuid, text, text) from public, anon;
grant execute on function public.sf_access_request(uuid, uuid, text, text) to authenticated;

-- Any admin decides, never their own request. Approval assigns the job role (idempotent).
create or replace function public.sf_access_decide(p_id uuid, p_approve boolean, p_note text)
returns text language plpgsql security definer set search_path = public as $$
declare r public.sf_access_requests; v_status text;
begin
  select * into r from public.sf_access_requests where id = p_id for update;
  if r.id is null or not public.sf_is_member(r.workspace_id) then raise exception 'request not found' using errcode = 'no_data_found'; end if;
  if not public.sf_has_role(r.workspace_id, array['admin']) then raise exception 'only admins decide access requests' using errcode = 'insufficient_privilege'; end if;
  if r.requested_by = auth.uid() then raise exception 'you cannot decide your own request' using errcode = 'insufficient_privilege'; end if;
  if r.status <> 'pending' then raise exception 'this request is already %', r.status using errcode = 'check_violation'; end if;
  v_status := case when p_approve then 'approved' else 'declined' end;
  update public.sf_access_requests set status = v_status, decided_by = auth.uid(), decided_at = now(), decision_note = nullif(left(coalesce(p_note, ''), 1000), '') where id = p_id;
  if p_approve and exists (select 1 from public.sf_memberships m where m.workspace_id = r.workspace_id and m.user_id = r.requested_by) then
    insert into public.sf_role_assignments (workspace_id, talent_id, user_id, granted_by)
    values (r.workspace_id, r.talent_id, r.requested_by, auth.uid())
    on conflict (talent_id, user_id) where user_id is not null do nothing;
  end if;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (r.workspace_id, auth.uid(), 'user', 'access.' || case when p_approve then 'approve' else 'decline' end, 'access_request', p_id::text,
          jsonb_build_object('talent_id', r.talent_id, 'requested_by', r.requested_by, 'note', p_note));
  return v_status;
end $$;
revoke all on function public.sf_access_decide(uuid, boolean, text) from public, anon;
grant execute on function public.sf_access_decide(uuid, boolean, text) to authenticated;

-- ── API catalogs (from 0005 / 0002), now with "allowed" for the calling key ──
create or replace function public.sf_api_catalog(p_key_hash text)
returns jsonb language plpgsql volatile security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; out jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select coalesce(jsonb_agg(jsonb_build_object(
           'slug', s.slug, 'name', s.name, 'purpose', s.purpose, 'version', v.version, 'version_id', v.id,
           'repo_skill', case when v.source->>'kind' = 'repo' then v.source->>'repo_skill' end,
           'inputs', v.manifest->'inputs', 'outputs', v.manifest->'outputs',
           'allowed', (public.sf_run_access(v_ws, v.id, null, v_key)->>'allowed')::boolean) order by s.slug), '[]'::jsonb)
  into out
  from public.sf_skills s join public.sf_skill_versions v on v.id = s.latest_version_id
  where s.workspace_id = v_ws and s.status = 'published' and v.status = 'published';
  return out;
end $$;
grant execute on function public.sf_api_catalog(text) to anon, authenticated;

create or replace function public.sf_api_skills(p_key_hash text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; out jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select coalesce(jsonb_agg(jsonb_build_object(
           'slug', s.slug, 'name', s.name, 'purpose', s.purpose, 'intended_users', s.intended_users, 'usage_guidance', s.usage_guidance,
           'version', v.version, 'version_id', v.id, 'published_at', v.published_at, 'manifest_hash', v.manifest_hash,
           'inputs', v.manifest->'inputs', 'outputs', v.manifest->'outputs',
           'allowed', (public.sf_run_access(v_ws, v.id, null, v_key)->>'allowed')::boolean) order by s.slug), '[]'::jsonb)
  into out
  from public.sf_skills s join public.sf_skill_versions v on v.id = s.latest_version_id
  where s.workspace_id = v_ws and s.status = 'published' and v.status = 'published';
  return out;
end $$;
grant execute on function public.sf_api_skills(text) to anon, authenticated;
