-- 0026: governed skills in Claude Code (and any agent that loads SKILL.md folders).
-- The factory publishes each skill's frozen, reviewed files (sf_version_snapshots) to a Claude Code plugin built by
-- scripts/build_plugin.py. The plugin's hook checks the files on disk against the published hash before a skill loads
-- and reports each load here, so the factory sees who used which approved version, and whether the files were intact.
-- Two RPCs, both keyed by an API key (anon role, security definer, like the other sf_api_* functions):
--   sf_api_skill_snapshot  the published version's frozen files + hash, only when the key may run that skill
--   sf_record_use          one row per load: version, integrity verdict, current/stale; never blocks the caller
-- Additive only.
-- rollback: (manual)
--   drop function if exists public.sf_record_use(text, text, int, text, text, text, text);
--   drop function if exists public.sf_api_skill_snapshot(text, text);
--   drop table if exists public.sf_skill_uses cascade;

create table if not exists public.sf_skill_uses (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.sf_workspaces(id) on delete cascade,
  skill_id     uuid not null references public.sf_skills(id) on delete cascade,
  version_id   uuid references public.sf_skill_versions(id) on delete set null,
  slug         text not null,
  version      int  not null check (version > 0),
  sha256       text check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$'),
  client       text not null check (client in ('claude-code')),
  event        text not null check (event in ('loaded', 'blocked')),
  integrity    text not null check (integrity in ('verified', 'modified', 'unknown')),
  currency     text not null check (currency in ('current', 'stale', 'unpublished')),
  session_ref  text check (session_ref is null or length(session_ref) <= 128),
  api_key_id   uuid,
  created_at   timestamptz not null default now()
);
create index if not exists sf_skill_uses_skill_idx on public.sf_skill_uses (skill_id, created_at desc);
create index if not exists sf_skill_uses_ws_idx on public.sf_skill_uses (workspace_id, created_at desc);

alter table public.sf_skill_uses enable row level security;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_skill_uses' and policyname='sf_skill_uses_select') then execute $p$
  create policy sf_skill_uses_select on public.sf_skill_uses for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if; end $$;
grant select on public.sf_skill_uses to authenticated;

-- The published version's frozen files. Null when the skill is not published, not frozen, or this key may not run it.
create or replace function public.sf_api_skill_snapshot(p_key_hash text, p_slug text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; out jsonb;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select jsonb_build_object(
           'slug', s.slug, 'name', s.name, 'purpose', s.purpose, 'version', v.version, 'version_id', v.id,
           'published_at', v.published_at, 'manifest_hash', v.manifest_hash, 'repo_skill', sn.repo_skill,
           'sha256', sn.sha256, 'files', sn.files)
    into out
    from public.sf_skills s
    join public.sf_skill_versions v on v.id = s.latest_version_id
    join public.sf_version_snapshots sn on sn.version_id = v.id
   where s.workspace_id = v_ws and s.slug = p_slug and s.status = 'published' and v.status = 'published'
     and coalesce((public.sf_run_access(v_ws, v.id, null, v_key)->>'allowed')::boolean, false);
  return out;
end $$;
revoke all on function public.sf_api_skill_snapshot(text, text) from public;
grant execute on function public.sf_api_skill_snapshot(text, text) to anon, authenticated;

-- One load of a skill in an agent. The version must be one this workspace released for that skill (never a draft).
create or replace function public.sf_record_use(p_key_hash text, p_slug text, p_version int, p_sha256 text, p_event text, p_integrity text, p_session text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_key uuid; s record; v record; v_currency text; v_id uuid;
begin
  select api_key_id, workspace_id into v_key, v_ws from public.sf_resolve_api_key(p_key_hash);
  if v_ws is null then raise exception 'invalid api key' using errcode = 'insufficient_privilege'; end if;
  select id, status, latest_version_id into s from public.sf_skills where workspace_id = v_ws and slug = p_slug;
  if s.id is null then raise exception 'unknown skill' using errcode = 'no_data_found'; end if;
  select id, status into v from public.sf_skill_versions where skill_id = s.id and version = p_version and status <> 'draft';
  if v.id is null then raise exception 'unknown version' using errcode = 'no_data_found'; end if;
  v_currency := case when s.status = 'published' and v.status = 'published' and v.id = s.latest_version_id then 'current'
                     when s.status = 'published' then 'stale' else 'unpublished' end;
  insert into public.sf_skill_uses (workspace_id, skill_id, version_id, slug, version, sha256, client, event, integrity, currency, session_ref, api_key_id)
  values (v_ws, s.id, v.id, p_slug, p_version, nullif(p_sha256, ''), 'claude-code', p_event, p_integrity, v_currency, left(p_session, 128), v_key)
  returning id into v_id;
  return jsonb_build_object('id', v_id, 'currency', v_currency);
end $$;
revoke all on function public.sf_record_use(text, text, int, text, text, text, text) from public;
grant execute on function public.sf_record_use(text, text, int, text, text, text, text) to anon, authenticated;
