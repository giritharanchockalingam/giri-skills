-- 0016_sf_invitations.sql — invite people who have no account yet: an admin records email + role; the invitation is
-- accepted by sf_accept_invitations() when that email signs in (never downgrading an existing membership).
-- Pending for 14 days unless revoked. sf_ prefix only; idempotent.
-- rollback: (manual — drops pending/accepted invitations; memberships they created stay)
--   drop function if exists public.sf_accept_invitations();
--   drop table if exists public.sf_invitations cascade;

create table if not exists public.sf_invitations (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  email         text not null check (email = lower(trim(email)) and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  role          text not null check (role in ('admin', 'author', 'reviewer', 'consumer')),
  invited_by    uuid not null references auth.users(id),
  created_at    timestamptz not null default now(),
  expires_at    timestamptz not null default now() + interval '14 days',
  accepted_at   timestamptz,
  accepted_by   uuid references auth.users(id),
  revoked_at    timestamptz
);
create unique index if not exists sf_invitations_pending_uq on public.sf_invitations (workspace_id, email) where accepted_at is null and revoked_at is null;
create index if not exists sf_invitations_email_idx on public.sf_invitations (email) where accepted_at is null and revoked_at is null;

alter table public.sf_invitations enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_invitations' and policyname='sf_invitations_select') then execute $p$
    create policy sf_invitations_select on public.sf_invitations for select to authenticated using (public.sf_has_role(workspace_id, array['admin'])) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_invitations' and policyname='sf_invitations_insert') then execute $p$
    create policy sf_invitations_insert on public.sf_invitations for insert to authenticated
    with check (public.sf_has_role(workspace_id, array['admin']) and invited_by = auth.uid() and accepted_at is null and revoked_at is null) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_invitations' and policyname='sf_invitations_update') then execute $p$
    create policy sf_invitations_update on public.sf_invitations for update to authenticated
    using (public.sf_has_role(workspace_id, array['admin'])) with check (public.sf_has_role(workspace_id, array['admin']) and accepted_at is null) $p$; end if;
end $$;
grant select, insert, update on public.sf_invitations to authenticated;

-- Called after sign-in: turns this user's pending invitations into memberships. Existing memberships are kept as they
-- are (an invitation never changes the role of someone already in the workspace).
create or replace function public.sf_accept_invitations()
returns int language plpgsql security definer set search_path = public as $$
declare v_email text; v_n int := 0; r public.sf_invitations;
begin
  if auth.uid() is null then return 0; end if;
  select lower(email) into v_email from auth.users where id = auth.uid();
  if v_email is null then return 0; end if;
  for r in select * from public.sf_invitations where email = v_email and accepted_at is null and revoked_at is null and expires_at > now() for update loop
    insert into public.sf_memberships (workspace_id, user_id, role) values (r.workspace_id, auth.uid(), r.role) on conflict (workspace_id, user_id) do nothing;
    update public.sf_invitations set accepted_at = now(), accepted_by = auth.uid() where id = r.id;
    insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
    values (r.workspace_id, auth.uid(), 'user', 'invitation.accept', 'invitation', r.id::text, jsonb_build_object('email', r.email, 'role', r.role));
    v_n := v_n + 1;
  end loop;
  return v_n;
end $$;
grant execute on function public.sf_accept_invitations() to authenticated;
revoke execute on function public.sf_accept_invitations() from anon, public;
