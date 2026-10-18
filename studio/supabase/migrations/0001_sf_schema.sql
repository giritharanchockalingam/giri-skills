-- 0001_sf_schema.sql — Skills Factory core schema (all objects prefixed sf_; idempotent).
-- Shared Supabase project: nothing here touches public.profiles or any non-sf_ object.
-- Apply with the Supabase SQL editor or `supabase db push`; re-running is safe.

create extension if not exists pgcrypto;

-- ───────────────────────────── helpers ─────────────────────────────

create or replace function public.sf_set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

-- ───────────────────────────── tables ─────────────────────────────

create table if not exists public.sf_workspaces (
  id          uuid primary key default gen_random_uuid(),
  name        text not null check (length(name) between 1 and 120),
  slug        text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  created_by  uuid not null references auth.users(id),
  created_at  timestamptz not null default now()
);

create table if not exists public.sf_memberships (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  user_id       uuid not null references auth.users(id) on delete cascade,
  role          text not null check (role in ('consumer','author','reviewer','admin')),
  created_at    timestamptz not null default now(),
  unique (workspace_id, user_id)
);
create index if not exists sf_memberships_user_idx on public.sf_memberships(user_id);

create table if not exists public.sf_policies (
  workspace_id        uuid primary key references public.sf_workspaces(id) on delete cascade,
  allowed_tools       jsonb not null default '["script","llm"]'::jsonb,
  allowed_providers   jsonb not null default '["none","anthropic"]'::jsonb,
  monthly_budget_usd  numeric(12,4),
  max_concurrency     int not null default 2 check (max_concurrency between 1 and 50),
  updated_at          timestamptz not null default now()
);

create table if not exists public.sf_skills (
  id                 uuid primary key default gen_random_uuid(),
  workspace_id       uuid not null references public.sf_workspaces(id) on delete cascade,
  slug               text not null check (slug ~ '^[a-z0-9][a-z0-9-]{0,78}$'),
  name               text not null check (length(name) between 1 and 160),
  owner_id           uuid not null references auth.users(id),
  purpose            text not null default '',
  intended_users     text not null default '',
  usage_guidance     text not null default '',
  status             text not null default 'draft' check (status in ('draft','published','retired')),
  latest_version_id  uuid,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (workspace_id, slug)
);

create table if not exists public.sf_skill_versions (
  id             uuid primary key default gen_random_uuid(),
  skill_id       uuid not null references public.sf_skills(id) on delete cascade,
  version        int not null check (version >= 1),
  status         text not null default 'draft'
                 check (status in ('draft','in_review','approved','published','superseded','retired')),
  manifest       jsonb not null,
  manifest_hash  text not null check (manifest_hash ~ '^[0-9a-f]{64}$'),
  source         jsonb not null default '{"kind":"authored"}'::jsonb,
  change_note    text not null default '',
  created_by     uuid not null references auth.users(id),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  published_at   timestamptz,
  unique (skill_id, version)
);
create index if not exists sf_skill_versions_skill_idx on public.sf_skill_versions(skill_id, version desc);

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'sf_skills_latest_version_fk') then
    alter table public.sf_skills add constraint sf_skills_latest_version_fk
      foreign key (latest_version_id) references public.sf_skill_versions(id) on delete set null;
  end if;
end $$;

create table if not exists public.sf_files (
  id          uuid primary key default gen_random_uuid(),
  version_id  uuid not null references public.sf_skill_versions(id) on delete cascade,
  path        text not null check (path ~ '^(scripts|assets|references)/[A-Za-z0-9._/-]{1,200}$' and path !~ '\.\.'),
  content     text not null check (length(content) <= 400000),
  sha256      text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  updated_at  timestamptz not null default now(),
  unique (version_id, path)
);

create table if not exists public.sf_eval_cases (
  id          uuid primary key default gen_random_uuid(),
  version_id  uuid not null references public.sf_skill_versions(id) on delete cascade,
  name        text not null check (length(name) between 1 and 160),
  inputs      jsonb not null default '{}'::jsonb,
  checks      jsonb not null default '[]'::jsonb,
  expected    jsonb not null default '{}'::jsonb,
  notes       text not null default '',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists sf_eval_cases_version_idx on public.sf_eval_cases(version_id);

create table if not exists public.sf_eval_runs (
  id             uuid primary key default gen_random_uuid(),
  version_id     uuid not null references public.sf_skill_versions(id) on delete cascade,
  eval_set_hash  text not null,
  status         text not null default 'running' check (status in ('running','finished','failed','cancelled')),
  pass_rate      numeric(5,4),
  results        jsonb not null default '[]'::jsonb,
  provider       text,
  model          text,
  started_at     timestamptz not null default now(),
  finished_at    timestamptz,
  created_by     uuid not null references auth.users(id)
);
create index if not exists sf_eval_runs_version_idx on public.sf_eval_runs(version_id, started_at desc);

create table if not exists public.sf_approvals (
  id             uuid primary key default gen_random_uuid(),
  version_id     uuid not null references public.sf_skill_versions(id) on delete cascade,
  manifest_hash  text not null,
  decision       text not null check (decision in ('approve','reject')),
  note           text not null default '',
  reviewer_id    uuid not null references auth.users(id),
  created_at     timestamptz not null default now()
);
create index if not exists sf_approvals_version_idx on public.sf_approvals(version_id, created_at desc);

create table if not exists public.sf_api_keys (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  name          text not null check (length(name) between 1 and 80),
  key_hash      text not null unique check (key_hash ~ '^[0-9a-f]{64}$'),
  prefix        text not null,
  created_by    uuid not null references auth.users(id),
  created_at    timestamptz not null default now(),
  last_used_at  timestamptz,
  revoked_at    timestamptz
);

create table if not exists public.sf_runs (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references public.sf_workspaces(id) on delete cascade,
  version_id       uuid not null references public.sf_skill_versions(id) on delete cascade,
  invoked_by       uuid references auth.users(id),
  api_key_id       uuid references public.sf_api_keys(id),
  source           text not null check (source in ('ui','api','eval')),
  status           text not null default 'queued'
                   check (status in ('queued','running','succeeded','failed','needs_input','timeout','cancelled')),
  idempotency_key  text,
  inputs_ref       jsonb not null default '[]'::jsonb,
  run_json         jsonb,
  outputs          jsonb not null default '[]'::jsonb,
  logs             text not null default '',
  provider         text,
  model            text,
  usage            jsonb,
  cost_usd         numeric(12,6),
  cost_is_estimate boolean not null default true,
  started_at       timestamptz,
  finished_at      timestamptz,
  duration_ms      int,
  error            text,
  created_at       timestamptz not null default now(),
  check (invoked_by is not null or api_key_id is not null)
);
create index if not exists sf_runs_ws_idx on public.sf_runs(workspace_id, created_at desc);
create index if not exists sf_runs_version_idx on public.sf_runs(version_id, created_at desc);
create unique index if not exists sf_runs_idem_idx on public.sf_runs(workspace_id, idempotency_key) where idempotency_key is not null;

create table if not exists public.sf_connections (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  kind          text not null check (kind in ('llm_provider','http','database','other')),
  name          text not null check (length(name) between 1 and 80),
  config        jsonb not null default '{}'::jsonb,
  secret_ref    text not null default '' check (secret_ref ~ '^[A-Z0-9_]{0,64}$'),
  status        text not null default 'unverified' check (status in ('unverified','configured','not_configured','disabled')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (workspace_id, name)
);

create table if not exists public.sf_audit_events (
  id            bigserial primary key,
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  actor_id      uuid,
  actor_kind    text not null check (actor_kind in ('user','api_key','system')),
  action        text not null,
  entity_type   text not null,
  entity_id     text,
  details       jsonb not null default '{}'::jsonb,
  created_at    timestamptz not null default now()
);
create index if not exists sf_audit_ws_idx on public.sf_audit_events(workspace_id, created_at desc);

-- ───────────────────────────── membership helpers (after the tables they read) ─────────────────────────────
-- The caller's role in a workspace (null when not a member). STABLE so policies can inline it.
create or replace function public.sf_role(p_workspace uuid) returns text
language sql stable security definer set search_path = public as $$
  select m.role from public.sf_memberships m
  where m.workspace_id = p_workspace and m.user_id = auth.uid()
  limit 1
$$;

create or replace function public.sf_is_member(p_workspace uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.sf_memberships m where m.workspace_id = p_workspace and m.user_id = auth.uid())
$$;

create or replace function public.sf_has_role(p_workspace uuid, p_roles text[]) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.sf_memberships m
                 where m.workspace_id = p_workspace and m.user_id = auth.uid() and m.role = any(p_roles))
$$;

-- ───────────────────────────── triggers ─────────────────────────────

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_skills_updated_at') then
    create trigger sf_skills_updated_at before update on public.sf_skills for each row execute function public.sf_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_skill_versions_updated_at') then
    create trigger sf_skill_versions_updated_at before update on public.sf_skill_versions for each row execute function public.sf_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_eval_cases_updated_at') then
    create trigger sf_eval_cases_updated_at before update on public.sf_eval_cases for each row execute function public.sf_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_connections_updated_at') then
    create trigger sf_connections_updated_at before update on public.sf_connections for each row execute function public.sf_set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_files_updated_at') then
    create trigger sf_files_updated_at before update on public.sf_files for each row execute function public.sf_set_updated_at();
  end if;
end $$;

-- Immutability + lifecycle guard for versions.
--  * manifest / manifest_hash / source may change only while status = 'draft'
--  * ordinary callers may only move draft <-> in_review and approved -> draft (reopen for editing: the
--    approval row keeps the reviewed hash, so any edit makes it visibly stale); every other transition
--    happens inside a SECURITY DEFINER RPC that sets the transaction-local flag sf.rpc = '1'
create or replace function public.sf_versions_guard() returns trigger
language plpgsql as $$
declare in_rpc boolean := coalesce(current_setting('sf.rpc', true), '') = '1';
begin
  if old.status <> 'draft' and (new.manifest is distinct from old.manifest
                                or new.manifest_hash is distinct from old.manifest_hash
                                or new.source is distinct from old.source) then
    raise exception 'sf_skill_versions: version % is % and immutable (create a new draft version)', old.version, old.status
      using errcode = 'check_violation';
  end if;
  if new.skill_id <> old.skill_id or new.version <> old.version then
    raise exception 'sf_skill_versions: skill_id/version cannot change' using errcode = 'check_violation';
  end if;
  if new.status <> old.status and not in_rpc then
    if not ((old.status = 'draft' and new.status = 'in_review') or (old.status = 'in_review' and new.status = 'draft')
            or (old.status = 'approved' and new.status = 'draft')) then
      raise exception 'sf_skill_versions: transition % -> % is only allowed through sf_publish_version / sf_retire_version / sf_review_version', old.status, new.status
        using errcode = 'check_violation';
    end if;
  end if;
  if new.published_at is distinct from old.published_at and not in_rpc then
    raise exception 'sf_skill_versions: published_at is set by sf_publish_version' using errcode = 'check_violation';
  end if;
  return new;
end $$;

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_skill_versions_guard') then
    create trigger sf_skill_versions_guard before update on public.sf_skill_versions for each row execute function public.sf_versions_guard();
  end if;
end $$;

-- Files belong to the manifest's content: frozen once the version leaves draft.
create or replace function public.sf_files_guard() returns trigger
language plpgsql as $$
declare v_status text; v_id uuid;
begin
  v_id := coalesce(new.version_id, old.version_id);
  select status into v_status from public.sf_skill_versions where id = v_id;
  if v_status is distinct from 'draft' and coalesce(current_setting('sf.rpc', true), '') <> '1' then
    raise exception 'sf_files: version is % and its files are immutable', v_status using errcode = 'check_violation';
  end if;
  return coalesce(new, old);
end $$;

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_files_guard') then
    create trigger sf_files_guard before insert or update or delete on public.sf_files for each row execute function public.sf_files_guard();
  end if;
end $$;

-- Approvals are append-only.
create or replace function public.sf_reject_change() returns trigger
language plpgsql as $$
begin
  raise exception '% rows are append-only', tg_table_name using errcode = 'check_violation';
end $$;

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_approvals_append_only') then
    create trigger sf_approvals_append_only before update or delete on public.sf_approvals for each row execute function public.sf_reject_change();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_audit_append_only') then
    create trigger sf_audit_append_only before update or delete on public.sf_audit_events for each row execute function public.sf_reject_change();
  end if;
end $$;

-- ───────────────────────────── row level security ─────────────────────────────

alter table public.sf_workspaces     enable row level security;
alter table public.sf_memberships    enable row level security;
alter table public.sf_policies       enable row level security;
alter table public.sf_skills         enable row level security;
alter table public.sf_skill_versions enable row level security;
alter table public.sf_files          enable row level security;
alter table public.sf_eval_cases     enable row level security;
alter table public.sf_eval_runs      enable row level security;
alter table public.sf_approvals      enable row level security;
alter table public.sf_api_keys       enable row level security;
alter table public.sf_runs           enable row level security;
alter table public.sf_connections    enable row level security;
alter table public.sf_audit_events   enable row level security;

-- drop + create keeps this file re-runnable
do $$
declare p record;
begin
  for p in select policyname, tablename from pg_policies where schemaname = 'public' and tablename like 'sf\_%' loop
    execute format('drop policy if exists %I on public.%I', p.policyname, p.tablename);
  end loop;
end $$;

-- workspaces: members read; creation happens in sf_create_workspace; admins rename
create policy sf_workspaces_select on public.sf_workspaces for select to authenticated using (public.sf_is_member(id));
create policy sf_workspaces_update on public.sf_workspaces for update to authenticated
  using (public.sf_has_role(id, array['admin'])) with check (public.sf_has_role(id, array['admin']));

-- memberships: members see their workspace's roster; admins manage it
create policy sf_memberships_select on public.sf_memberships for select to authenticated using (public.sf_is_member(workspace_id));
create policy sf_memberships_insert on public.sf_memberships for insert to authenticated with check (public.sf_has_role(workspace_id, array['admin']));
create policy sf_memberships_update on public.sf_memberships for update to authenticated
  using (public.sf_has_role(workspace_id, array['admin'])) with check (public.sf_has_role(workspace_id, array['admin']));
create policy sf_memberships_delete on public.sf_memberships for delete to authenticated
  using (public.sf_has_role(workspace_id, array['admin']) and user_id <> auth.uid());

-- policies: members read; admins write
create policy sf_policies_select on public.sf_policies for select to authenticated using (public.sf_is_member(workspace_id));
create policy sf_policies_insert on public.sf_policies for insert to authenticated with check (public.sf_has_role(workspace_id, array['admin']));
create policy sf_policies_update on public.sf_policies for update to authenticated
  using (public.sf_has_role(workspace_id, array['admin'])) with check (public.sf_has_role(workspace_id, array['admin']));

-- skills: members read; authors/admins create and edit; admins delete
create policy sf_skills_select on public.sf_skills for select to authenticated using (public.sf_is_member(workspace_id));
create policy sf_skills_insert on public.sf_skills for insert to authenticated
  with check (public.sf_has_role(workspace_id, array['author','admin']) and owner_id = auth.uid());
create policy sf_skills_update on public.sf_skills for update to authenticated
  using (public.sf_has_role(workspace_id, array['author','admin'])) with check (public.sf_has_role(workspace_id, array['author','admin']));
create policy sf_skills_delete on public.sf_skills for delete to authenticated using (public.sf_has_role(workspace_id, array['admin']));

-- versions: members read; authors/admins create drafts and edit (trigger enforces immutability)
create policy sf_versions_select on public.sf_skill_versions for select to authenticated
  using (exists (select 1 from public.sf_skills s where s.id = skill_id and public.sf_is_member(s.workspace_id)));
create policy sf_versions_insert on public.sf_skill_versions for insert to authenticated
  with check (status = 'draft' and created_by = auth.uid()
              and exists (select 1 from public.sf_skills s where s.id = skill_id and public.sf_has_role(s.workspace_id, array['author','admin'])));
create policy sf_versions_update on public.sf_skill_versions for update to authenticated
  using (exists (select 1 from public.sf_skills s where s.id = skill_id and public.sf_has_role(s.workspace_id, array['author','admin'])))
  with check (exists (select 1 from public.sf_skills s where s.id = skill_id and public.sf_has_role(s.workspace_id, array['author','admin'])));
create policy sf_versions_delete on public.sf_skill_versions for delete to authenticated
  using (status = 'draft' and exists (select 1 from public.sf_skills s where s.id = skill_id and public.sf_has_role(s.workspace_id, array['author','admin'])));

-- files / eval cases: members read; authors/admins write
create policy sf_files_select on public.sf_files for select to authenticated
  using (exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = version_id and public.sf_is_member(s.workspace_id)));
create policy sf_files_write on public.sf_files for all to authenticated
  using (exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = version_id and public.sf_has_role(s.workspace_id, array['author','admin'])))
  with check (exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = version_id and public.sf_has_role(s.workspace_id, array['author','admin'])));

create policy sf_eval_cases_select on public.sf_eval_cases for select to authenticated
  using (exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = version_id and public.sf_is_member(s.workspace_id)));
create policy sf_eval_cases_write on public.sf_eval_cases for all to authenticated
  using (exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = version_id and public.sf_has_role(s.workspace_id, array['author','admin'])))
  with check (exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = version_id and public.sf_has_role(s.workspace_id, array['author','admin'])));

-- eval runs: members read; authors/reviewers/admins start; the starter records progress
create policy sf_eval_runs_select on public.sf_eval_runs for select to authenticated
  using (exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = version_id and public.sf_is_member(s.workspace_id)));
create policy sf_eval_runs_insert on public.sf_eval_runs for insert to authenticated
  with check (created_by = auth.uid() and exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = version_id and public.sf_has_role(s.workspace_id, array['author','reviewer','admin'])));
create policy sf_eval_runs_update on public.sf_eval_runs for update to authenticated
  using (created_by = auth.uid()) with check (created_by = auth.uid());

-- approvals: members read; reviewers/admins decide on versions that are in review; append-only
create policy sf_approvals_select on public.sf_approvals for select to authenticated
  using (exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id where v.id = version_id and public.sf_is_member(s.workspace_id)));
create policy sf_approvals_insert on public.sf_approvals for insert to authenticated
  with check (reviewer_id = auth.uid()
              and exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id
                          where v.id = sf_approvals.version_id and v.status = 'in_review' and v.manifest_hash = sf_approvals.manifest_hash
                            and public.sf_has_role(s.workspace_id, array['reviewer','admin'])));

-- api keys: admins only (the hash is stored; the key itself is shown once at creation)
create policy sf_api_keys_all on public.sf_api_keys for all to authenticated
  using (public.sf_has_role(workspace_id, array['admin'])) with check (public.sf_has_role(workspace_id, array['admin']));

-- runs: members read their workspace's runs; any member may run a published version, authors/reviewers/admins any version
create policy sf_runs_select on public.sf_runs for select to authenticated using (public.sf_is_member(workspace_id));
create policy sf_runs_insert on public.sf_runs for insert to authenticated
  with check (invoked_by = auth.uid() and public.sf_is_member(workspace_id)
              and exists (select 1 from public.sf_skill_versions v join public.sf_skills s on s.id = v.skill_id
                          where v.id = version_id and s.workspace_id = sf_runs.workspace_id
                            and (v.status = 'published' or public.sf_has_role(s.workspace_id, array['author','reviewer','admin']))));
create policy sf_runs_update on public.sf_runs for update to authenticated
  using (invoked_by = auth.uid()) with check (invoked_by = auth.uid());

-- connections: members read; admins manage
create policy sf_connections_select on public.sf_connections for select to authenticated using (public.sf_is_member(workspace_id));
create policy sf_connections_write on public.sf_connections for all to authenticated
  using (public.sf_has_role(workspace_id, array['admin'])) with check (public.sf_has_role(workspace_id, array['admin']));

-- audit: members read; writes go through sf_audit()
create policy sf_audit_select on public.sf_audit_events for select to authenticated using (public.sf_is_member(workspace_id));

-- ───────────────────────────── grants ─────────────────────────────
-- only the sf_ objects: nothing else in the shared project is touched
grant select, insert, update, delete on public.sf_workspaces, public.sf_memberships, public.sf_policies, public.sf_skills,
  public.sf_skill_versions, public.sf_files, public.sf_eval_cases, public.sf_eval_runs, public.sf_approvals, public.sf_api_keys,
  public.sf_runs, public.sf_connections, public.sf_audit_events to authenticated;
revoke all on public.sf_workspaces, public.sf_memberships, public.sf_policies, public.sf_skills, public.sf_skill_versions,
  public.sf_files, public.sf_eval_cases, public.sf_eval_runs, public.sf_approvals, public.sf_api_keys, public.sf_runs,
  public.sf_connections, public.sf_audit_events from anon;
grant usage, select on sequence public.sf_audit_events_id_seq to authenticated;
