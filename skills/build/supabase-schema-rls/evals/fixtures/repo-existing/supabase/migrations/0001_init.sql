-- 0001_init.sql (fictional eval fixture) — applied long ago, before the team's rollback convention.
create table public.projects (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  owner_id uuid not null
);
alter table public.projects enable row level security;
create policy projects_all on public.projects for all using (true);
