-- 0001_projects.sql (fictional eval fixture: a single-tenant app before tenancy was added)
create table public.projects (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);
alter table public.projects enable row level security;
create policy projects_select_owner on public.projects for select to authenticated
  using (created_by = (select auth.uid()));

create table public.project_exports (
  id         uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id),
  created_at timestamptz not null default now()
);
-- rollback:
-- drop table public.project_exports; drop table public.projects;
