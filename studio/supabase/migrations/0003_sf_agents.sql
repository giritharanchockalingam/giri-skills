-- 0003_sf_agents.sql — composed agents: configuration (versioned, published versions immutable) and runs.
-- Idempotent and non-destructive (create if not exists / guarded policies), sf_ prefix only.
-- rollback: (manual, in this order — drops everything this migration created; data in these tables is lost)
--   drop table if exists public.sf_agent_runs cascade;
--   drop table if exists public.sf_agent_versions cascade;
--   drop table if exists public.sf_agents cascade;
--   drop function if exists public.sf_publish_agent_version(uuid);
--   drop function if exists public.sf_agent_versions_guard();

create table if not exists public.sf_agents (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  slug          text not null check (slug ~ '^[a-z0-9][a-z0-9-]{0,78}$'),
  name          text not null check (length(name) between 1 and 160),
  description   text not null default '',
  owner_id      uuid not null references auth.users(id),
  status        text not null default 'draft' check (status in ('draft','published','retired')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (workspace_id, slug)
);

create table if not exists public.sf_agent_versions (
  id            uuid primary key default gen_random_uuid(),
  agent_id      uuid not null references public.sf_agents(id) on delete cascade,
  version       int not null check (version >= 1),
  status        text not null default 'draft' check (status in ('draft','published','superseded')),
  spec          jsonb not null,
  spec_hash     text not null check (spec_hash ~ '^[0-9a-f]{64}$'),
  change_note   text not null default '',
  created_by    uuid not null references auth.users(id),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  published_at  timestamptz,
  unique (agent_id, version)
);
create index if not exists sf_agent_versions_agent_idx on public.sf_agent_versions(agent_id, version desc);

create table if not exists public.sf_agent_runs (
  id                uuid primary key default gen_random_uuid(),
  workspace_id      uuid not null references public.sf_workspaces(id) on delete cascade,
  agent_version_id  uuid not null references public.sf_agent_versions(id) on delete cascade,
  invoked_by        uuid not null references auth.users(id),
  status            text not null default 'running'
                    check (status in ('running','awaiting_approval','blocked','failed','succeeded','needs_input','cancelled')),
  inputs            jsonb not null default '{}'::jsonb,
  cursor            int not null default 0 check (cursor >= 0),
  steps             jsonb not null default '[]'::jsonb,
  cost_usd          numeric(12,6),
  error             text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  finished_at       timestamptz
);
create index if not exists sf_agent_runs_ws_idx on public.sf_agent_runs(workspace_id, created_at desc);
create index if not exists sf_agent_runs_version_idx on public.sf_agent_runs(agent_version_id, created_at desc);

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_agents_updated_at') then
    create trigger sf_agents_updated_at before update on public.sf_agents for each row execute function public.sf_set_updated_at(); end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_agent_versions_updated_at') then
    create trigger sf_agent_versions_updated_at before update on public.sf_agent_versions for each row execute function public.sf_set_updated_at(); end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_agent_runs_updated_at') then
    create trigger sf_agent_runs_updated_at before update on public.sf_agent_runs for each row execute function public.sf_set_updated_at(); end if;
end $$;

-- A published (or superseded) agent version is frozen: its spec is what consumers and the API ran.
create or replace function public.sf_agent_versions_guard() returns trigger
language plpgsql set search_path = public as $$
declare in_rpc boolean := coalesce(current_setting('sf.rpc', true), '') = '1';
begin
  if old.status <> 'draft' and (new.spec is distinct from old.spec or new.spec_hash is distinct from old.spec_hash) then
    raise exception 'sf_agent_versions: version % is % and immutable (create a new draft version)', old.version, old.status
      using errcode = 'check_violation';
  end if;
  if new.agent_id <> old.agent_id or new.version <> old.version then
    raise exception 'sf_agent_versions: agent_id/version cannot change' using errcode = 'check_violation';
  end if;
  if (new.status <> old.status or new.published_at is distinct from old.published_at) and not in_rpc then
    raise exception 'sf_agent_versions: status changes only through sf_publish_agent_version' using errcode = 'check_violation';
  end if;
  return new;
end $$;
do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_agent_versions_guard') then
    create trigger sf_agent_versions_guard before update on public.sf_agent_versions for each row execute function public.sf_agent_versions_guard(); end if;
end $$;

alter table public.sf_agents         enable row level security;
alter table public.sf_agent_versions enable row level security;
alter table public.sf_agent_runs     enable row level security;

-- agents: members read; authors/admins create and edit; admins delete
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_agents' and policyname='sf_agents_select') then execute $p$
  create policy sf_agents_select on public.sf_agents for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_agents' and policyname='sf_agents_insert') then execute $p$
  create policy sf_agents_insert on public.sf_agents for insert to authenticated
  with check (public.sf_has_role(workspace_id, array['author','admin']) and owner_id = auth.uid()) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_agents' and policyname='sf_agents_update') then execute $p$
  create policy sf_agents_update on public.sf_agents for update to authenticated
  using (public.sf_has_role(workspace_id, array['author','admin'])) with check (public.sf_has_role(workspace_id, array['author','admin'])) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_agents' and policyname='sf_agents_delete') then execute $p$
  create policy sf_agents_delete on public.sf_agents for delete to authenticated using (public.sf_has_role(workspace_id, array['admin'])) $p$; end if; end $$;

-- versions: members read; authors/admins create; drafts editable by authors/admins (the guard freezes the rest)
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_agent_versions' and policyname='sf_agent_versions_select') then execute $p$
  create policy sf_agent_versions_select on public.sf_agent_versions for select to authenticated
  using (exists (select 1 from public.sf_agents a where a.id = agent_id and public.sf_is_member(a.workspace_id))) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_agent_versions' and policyname='sf_agent_versions_insert') then execute $p$
  create policy sf_agent_versions_insert on public.sf_agent_versions for insert to authenticated
  with check (created_by = auth.uid() and status = 'draft'
              and exists (select 1 from public.sf_agents a where a.id = agent_id and public.sf_has_role(a.workspace_id, array['author','admin']))) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_agent_versions' and policyname='sf_agent_versions_update') then execute $p$
  create policy sf_agent_versions_update on public.sf_agent_versions for update to authenticated
  using (exists (select 1 from public.sf_agents a where a.id = agent_id and public.sf_has_role(a.workspace_id, array['author','admin'])))
  with check (exists (select 1 from public.sf_agents a where a.id = agent_id and public.sf_has_role(a.workspace_id, array['author','admin']))) $p$; end if; end $$;

-- runs: members read their workspace's runs; members start runs as themselves; the invoker, reviewers and admins
-- advance them (approvals are recorded in steps with the approver's id; who may approve is checked in the API)
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_agent_runs' and policyname='sf_agent_runs_select') then execute $p$
  create policy sf_agent_runs_select on public.sf_agent_runs for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_agent_runs' and policyname='sf_agent_runs_insert') then execute $p$
  create policy sf_agent_runs_insert on public.sf_agent_runs for insert to authenticated
  with check (invoked_by = auth.uid() and public.sf_is_member(workspace_id)) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_agent_runs' and policyname='sf_agent_runs_update') then execute $p$
  create policy sf_agent_runs_update on public.sf_agent_runs for update to authenticated
  using (invoked_by = auth.uid() or public.sf_has_role(workspace_id, array['reviewer','admin']))
  with check (public.sf_is_member(workspace_id)) $p$; end if; end $$;

grant select, insert, update, delete on public.sf_agents, public.sf_agent_versions, public.sf_agent_runs to authenticated;

-- Publish: reviewers/admins freeze a draft; the previous published version becomes superseded.
create or replace function public.sf_publish_agent_version(p_version uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v record;
begin
  select av.*, a.workspace_id, a.id as aid into v
    from public.sf_agent_versions av join public.sf_agents a on a.id = av.agent_id where av.id = p_version;
  if v is null then raise exception 'agent version not found' using errcode = 'no_data_found'; end if;
  if not public.sf_has_role(v.workspace_id, array['reviewer','admin']) then
    raise exception 'reviewers or admins only' using errcode = 'insufficient_privilege';
  end if;
  if v.status <> 'draft' then raise exception 'version is % and cannot be published', v.status using errcode = 'check_violation'; end if;
  perform set_config('sf.rpc', '1', true);
  update public.sf_agent_versions set status = 'superseded' where agent_id = v.aid and status = 'published';
  update public.sf_agent_versions set status = 'published', published_at = now() where id = p_version;
  update public.sf_agents set status = 'published' where id = v.aid;
  perform set_config('sf.rpc', '', true);
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v.workspace_id, auth.uid(), 'user', 'agent.publish', 'agent_version', p_version::text,
          jsonb_build_object('version', v.version, 'spec_hash', v.spec_hash));
  return jsonb_build_object('version_id', p_version, 'version', v.version, 'status', 'published');
end $$;
grant execute on function public.sf_publish_agent_version(uuid) to authenticated;
