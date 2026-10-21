-- 0021: frozen files for repo-skill versions past draft (immutable versions).
-- A library skill's files change as the library improves; a version that was reviewed, approved or published must keep
-- running on the exact files it was reviewed with. The server copies those files here once (when review is requested,
-- or on first run while the deployment still holds them) and the runtime runs the version from this copy.
-- Written only by the server with the service key (no insert/update/delete grant); rows never change.
-- rollback: (manual) drop table if exists public.sf_version_snapshots cascade; drop function if exists public.sf_snapshot_immutable();

create table if not exists public.sf_version_snapshots (
  version_id   uuid primary key references public.sf_skill_versions(id) on delete cascade,
  workspace_id uuid not null references public.sf_workspaces(id) on delete cascade,
  repo_skill   text not null check (repo_skill ~ '^[a-z0-9-]+/[a-z0-9-]+$'),
  content_sha  text not null check (content_sha ~ '^[0-9a-f]{64}$'),   -- the deployment pin the files were taken at (= version's pin)
  sha256       text not null check (sha256 ~ '^[0-9a-f]{64}$'),        -- over the files themselves, sorted by path
  files        jsonb not null check (jsonb_typeof(files) = 'array' and jsonb_array_length(files) > 0),
  bytes        integer not null check (bytes > 0 and bytes <= 8000000),
  created_at   timestamptz not null default now()
);
create index if not exists sf_version_snapshots_ws_idx on public.sf_version_snapshots (workspace_id);

alter table public.sf_version_snapshots enable row level security;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_version_snapshots' and policyname='sf_version_snapshots_select') then execute $p$
  create policy sf_version_snapshots_select on public.sf_version_snapshots for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if; end $$;
grant select on public.sf_version_snapshots to authenticated;

create or replace function public.sf_snapshot_immutable() returns trigger language plpgsql set search_path = public as $$
begin
  raise exception 'sf_version_snapshots rows are immutable' using errcode = 'check_violation';
end $$;
do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_version_snapshots_immutable') then
    create trigger sf_version_snapshots_immutable before update on public.sf_version_snapshots for each row execute function public.sf_snapshot_immutable();
  end if;
end $$;
