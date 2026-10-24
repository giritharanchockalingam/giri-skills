-- 0025: Skills Factory × Port sync (spec §5.1 publish sync, §6.3 reconcile) — WP1.
-- Transactional outbox: the same transaction that publishes or retires a version writes an outbox row (trigger on
-- sf_skill_versions), so Port being down never blocks a release and nothing is dropped silently. A worker
-- (lib/integrations/port/outbox.ts, service role) drains it with backoff; after 5 attempts a row is dead-lettered and
-- shown on Integrations → Port. sf_port_links records what Port last received per skill (hash, version, status) so the
-- reconcile check compares the factory's truth with Port's copy. Additive only.
-- rollback: (manual)
--   drop trigger if exists sf_port_enqueue_trg on public.sf_skill_versions;
--   drop function if exists public.sf_port_enqueue();
--   drop function if exists public.sf_port_enqueue_all(uuid);
--   drop table if exists public.sf_port_outbox cascade;
--   drop table if exists public.sf_port_links cascade;

create table if not exists public.sf_port_outbox (
  id              uuid primary key default gen_random_uuid(),
  workspace_id    uuid not null references public.sf_workspaces(id) on delete cascade,
  skill_id        uuid not null references public.sf_skills(id) on delete cascade,
  skill_slug      text not null,
  event_type      text not null check (event_type in ('publish','retire')),
  payload         jsonb not null default '{}'::jsonb,
  attempts        int not null default 0 check (attempts >= 0),
  last_error      text,
  next_attempt_at timestamptz not null default now(),
  processed_at    timestamptz,
  created_at      timestamptz not null default now()
);
create index if not exists sf_port_outbox_pending_idx on public.sf_port_outbox(next_attempt_at) where processed_at is null;
create index if not exists sf_port_outbox_ws_idx on public.sf_port_outbox(workspace_id, created_at desc);

create table if not exists public.sf_port_links (
  workspace_id        uuid not null references public.sf_workspaces(id) on delete cascade,
  skill_id            uuid not null references public.sf_skills(id) on delete cascade,
  port_blueprint      text not null,
  port_entity_id      text not null,
  last_synced_hash    text,
  last_synced_version int,
  last_synced_status  text check (last_synced_status in ('published','retired')),
  last_synced_at      timestamptz,
  last_error          text,
  primary key (workspace_id, skill_id)
);

alter table public.sf_port_outbox enable row level security;
alter table public.sf_port_links  enable row level security;
-- members read (the Integrations page shows sync state); only the service-role worker writes.
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_port_outbox' and policyname='sf_port_outbox_select') then execute $p$ create policy sf_port_outbox_select on public.sf_port_outbox for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_port_links' and policyname='sf_port_links_select') then execute $p$ create policy sf_port_links_select on public.sf_port_links for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if; end $$;
grant select on public.sf_port_outbox, public.sf_port_links to authenticated;

-- The outbox row is written by the publish / retire transaction itself (sf_publish_version, sf_retire_version flip
-- the version status; this fires inside them). Superseding the previous version is covered by the new publish event.
create or replace function public.sf_port_enqueue()
returns trigger language plpgsql security definer set search_path = public as $$
declare v_ws uuid; v_slug text; v_event text;
begin
  if new.status = 'published' and old.status is distinct from 'published' then v_event := 'publish';
  elsif new.status = 'retired' and old.status = 'published' then v_event := 'retire';
  else return new; end if;
  select s.workspace_id, s.slug into v_ws, v_slug from public.sf_skills s where s.id = new.skill_id;
  insert into public.sf_port_outbox (workspace_id, skill_id, skill_slug, event_type, payload)
  values (v_ws, new.skill_id, v_slug, v_event,
          jsonb_build_object('version_id', new.id, 'version', new.version, 'manifest_hash', new.manifest_hash));
  return new;
end $$;

drop trigger if exists sf_port_enqueue_trg on public.sf_skill_versions;
create trigger sf_port_enqueue_trg after update of status on public.sf_skill_versions
  for each row execute function public.sf_port_enqueue();

-- Backfill / full resync (admins): one publish event per published skill, one retire event per retired skill with a
-- retired version. Idempotent in effect: the worker upserts on a deterministic entity identifier.
create or replace function public.sf_port_enqueue_all(p_workspace uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v_n int;
begin
  if public.sf_role(p_workspace) <> 'admin' then raise exception 'administrators only' using errcode = 'insufficient_privilege'; end if;
  with live as (
    select s.id, s.workspace_id, s.slug, v.id as version_id, v.version, v.manifest_hash, s.status
    from public.sf_skills s
    join lateral (
      select v2.* from public.sf_skill_versions v2 where v2.skill_id = s.id and v2.status = s.status
      order by v2.version desc limit 1
    ) v on true
    where s.workspace_id = p_workspace and s.status in ('published','retired')
  ), ins as (
    insert into public.sf_port_outbox (workspace_id, skill_id, skill_slug, event_type, payload)
    select workspace_id, id, slug, case status when 'published' then 'publish' else 'retire' end,
           jsonb_build_object('version_id', version_id, 'version', version, 'manifest_hash', manifest_hash, 'backfill', true)
    from live
    returning 1
  ) select count(*) into v_n from ins;
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (p_workspace, auth.uid(), 'user', 'integration.port.enqueue_all', 'integration', 'port', jsonb_build_object('events', v_n));
  return jsonb_build_object('ok', true, 'events', v_n);
end $$;
grant execute on function public.sf_port_enqueue_all(uuid) to authenticated;

-- Owner e-mails for the sync worker (service role only; auth.users is not readable through PostgREST).
create or replace function public.sf_port_skill_owners(p_workspace uuid)
returns table (skill_id uuid, email text)
language sql security definer set search_path = public stable as $$
  select s.id, u.email::text from public.sf_skills s join auth.users u on u.id = s.owner_id where s.workspace_id = p_workspace
$$;
revoke all on function public.sf_port_skill_owners(uuid) from public, anon, authenticated;
grant execute on function public.sf_port_skill_owners(uuid) to service_role;
