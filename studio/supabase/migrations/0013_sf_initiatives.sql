-- 0013_sf_initiatives.sql — initiatives: a goal over the catalog ("every repository at Silver by 1 Dec"), with an
-- owner and a deadline. Progress is never stored: it is computed from the live scorecard (sf_scorecard_latest), so it
-- cannot drift from the verdicts. sf_ prefix only; idempotent.
-- Writers: authors and admins create and change initiatives (RLS); members read them. Changes are audited by the app.
-- rollback: (manual — drops initiatives only; scorecards are untouched)
--   drop table if exists public.sf_initiatives cascade;

create table if not exists public.sf_initiatives (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  title         text not null check (length(title) between 1 and 140),
  description   text not null default '' check (length(description) <= 2000),
  target_level  text not null check (target_level in ('bronze', 'silver', 'gold')),
  repos         text[] not null default '{}',             -- owner/name keys; empty = every catalog repository a check applies to
  owner         text not null check (length(owner) between 1 and 120),   -- the accountable person or team, as named
  due_on        date not null,
  status        text not null default 'active' check (status in ('active', 'closed')),
  created_by    uuid not null references auth.users(id),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists sf_initiatives_ws_idx on public.sf_initiatives (workspace_id, status, due_on);

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_initiatives_updated_at') then
    create trigger sf_initiatives_updated_at before update on public.sf_initiatives for each row execute function public.sf_set_updated_at(); end if;
end $$;

alter table public.sf_initiatives enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_initiatives' and policyname='sf_initiatives_select') then execute $p$
    create policy sf_initiatives_select on public.sf_initiatives for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_initiatives' and policyname='sf_initiatives_insert') then execute $p$
    create policy sf_initiatives_insert on public.sf_initiatives for insert to authenticated
    with check (public.sf_has_role(workspace_id, array['author', 'admin']) and created_by = auth.uid()) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_initiatives' and policyname='sf_initiatives_update') then execute $p$
    create policy sf_initiatives_update on public.sf_initiatives for update to authenticated
    using (public.sf_has_role(workspace_id, array['author', 'admin'])) with check (public.sf_has_role(workspace_id, array['author', 'admin'])) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_initiatives' and policyname='sf_initiatives_delete') then execute $p$
    create policy sf_initiatives_delete on public.sf_initiatives for delete to authenticated using (public.sf_has_role(workspace_id, array['admin'])) $p$; end if;
end $$;
grant select, insert, update, delete on public.sf_initiatives to authenticated;
