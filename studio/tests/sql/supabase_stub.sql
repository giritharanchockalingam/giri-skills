-- Stand-in for the parts of a Supabase project the sf_ migrations depend on. Test use only
-- (tests/sql/run.sh); never applied to the real project.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
end $$;
create schema if not exists auth;
create table auth.users (id uuid primary key, email text unique, created_at timestamptz default now());
-- Supabase's auth.uid() reads the JWT claim; the test harness sets request.jwt.claim.sub instead.
create or replace function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
grant usage on schema auth to anon, authenticated;
grant usage on schema public to anon, authenticated;
-- the shared project has other apps' tables; this one proves the migrations never touch them
create table public.profiles (id uuid primary key, email text, full_name text, role text);
