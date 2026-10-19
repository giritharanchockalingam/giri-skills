-- 0007_sf_catalog.sql — Context Lake v1: a workspace's GitHub App installations and the catalog of what they expose
-- (repositories now; services, deployments, incidents later), plus a log of every sync. sf_ prefix only; idempotent.
-- Writes go through the signed-in user's session (RLS): installations by admins, catalog sync by authors/admins.
-- rollback: (manual, in this order — drops everything this migration created; catalog data is lost, GitHub is unaffected)
--   drop table if exists public.sf_catalog_syncs cascade;
--   drop table if exists public.sf_catalog_entities cascade;
--   drop table if exists public.sf_github_installations cascade;

create table if not exists public.sf_github_installations (
  id                    uuid primary key default gen_random_uuid(),
  workspace_id          uuid not null references public.sf_workspaces(id) on delete cascade,
  installation_id       bigint not null unique,            -- one workspace per installation: no cross-tenant reads
  account_login         text not null check (length(account_login) between 1 and 100),
  account_type          text not null default 'User' check (account_type in ('User', 'Organization')),
  repository_selection  text not null default 'selected' check (repository_selection in ('all', 'selected')),
  verified_by           uuid not null references auth.users(id),   -- the GitHub user who proved access was signed in as this user
  suspended_at          timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
create index if not exists sf_github_installations_ws_idx on public.sf_github_installations(workspace_id);

create table if not exists public.sf_catalog_entities (
  id                uuid primary key default gen_random_uuid(),
  workspace_id      uuid not null references public.sf_workspaces(id) on delete cascade,
  kind              text not null check (kind in ('repository')),
  source            text not null default 'github' check (source in ('github')),
  key               text not null check (length(key) between 1 and 200),       -- owner/name
  external_id       text not null,                                             -- GitHub repository id
  installation_id   bigint references public.sf_github_installations(installation_id) on delete set null,
  title             text not null,
  url               text not null check (url ~ '^https://'),
  owner             text,                                                      -- from CODEOWNERS (default rule), else null
  properties        jsonb not null default '{}'::jsonb,                        -- stack, languages, branch, visibility, signals
  archived          boolean not null default false,
  last_activity_at  timestamptz,
  synced_at         timestamptz not null default now(),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (workspace_id, kind, key)
);
create index if not exists sf_catalog_entities_ws_idx on public.sf_catalog_entities(workspace_id, kind, key);

create table if not exists public.sf_catalog_syncs (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references public.sf_workspaces(id) on delete cascade,
  installation_id  bigint,
  status           text not null default 'running' check (status in ('running', 'succeeded', 'failed')),
  counts           jsonb not null default '{}'::jsonb,
  error            text,
  started_by       uuid not null references auth.users(id),
  started_at       timestamptz not null default now(),
  finished_at      timestamptz
);
create index if not exists sf_catalog_syncs_ws_idx on public.sf_catalog_syncs(workspace_id, started_at desc);

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_github_installations_updated_at') then
    create trigger sf_github_installations_updated_at before update on public.sf_github_installations for each row execute function public.sf_set_updated_at(); end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_catalog_entities_updated_at') then
    create trigger sf_catalog_entities_updated_at before update on public.sf_catalog_entities for each row execute function public.sf_set_updated_at(); end if;
end $$;

alter table public.sf_github_installations enable row level security;
alter table public.sf_catalog_entities     enable row level security;
alter table public.sf_catalog_syncs        enable row level security;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_github_installations' and policyname='sf_gh_inst_select') then execute $p$
    create policy sf_gh_inst_select on public.sf_github_installations for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_github_installations' and policyname='sf_gh_inst_write') then execute $p$
    create policy sf_gh_inst_write on public.sf_github_installations for all to authenticated
    using (public.sf_has_role(workspace_id, array['admin'])) with check (public.sf_has_role(workspace_id, array['admin']) and verified_by = auth.uid()) $p$; end if;

  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_catalog_entities' and policyname='sf_catalog_select') then execute $p$
    create policy sf_catalog_select on public.sf_catalog_entities for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_catalog_entities' and policyname='sf_catalog_write') then execute $p$
    create policy sf_catalog_write on public.sf_catalog_entities for all to authenticated
    using (public.sf_has_role(workspace_id, array['author', 'admin'])) with check (public.sf_has_role(workspace_id, array['author', 'admin'])) $p$; end if;

  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_catalog_syncs' and policyname='sf_catalog_syncs_select') then execute $p$
    create policy sf_catalog_syncs_select on public.sf_catalog_syncs for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_catalog_syncs' and policyname='sf_catalog_syncs_write') then execute $p$
    create policy sf_catalog_syncs_write on public.sf_catalog_syncs for all to authenticated
    using (public.sf_has_role(workspace_id, array['author', 'admin'])) with check (public.sf_has_role(workspace_id, array['author', 'admin']) and started_by = auth.uid()) $p$; end if;
end $$;

grant select, insert, update, delete on public.sf_github_installations, public.sf_catalog_entities, public.sf_catalog_syncs to authenticated;
