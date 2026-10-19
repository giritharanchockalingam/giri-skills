-- 0004_sf_talent.sql — roles (a set of skills + playbooks) and talent pools (a team of roles), versioned like agents:
-- drafts editable by authors/admins, publish by reviewers/admins through an RPC, published specs frozen.
-- Idempotent and non-destructive (create if not exists / guarded policies), sf_ prefix only.

create table if not exists public.sf_talent (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.sf_workspaces(id) on delete cascade,
  kind          text not null check (kind in ('role','pool')),
  slug          text not null check (slug ~ '^[a-z0-9][a-z0-9-]{0,78}$'),
  name          text not null check (length(name) between 1 and 160),
  description   text not null default '',
  based_on      text,
  owner_id      uuid not null references auth.users(id),
  status        text not null default 'draft' check (status in ('draft','published','retired')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (workspace_id, kind, slug)
);
create index if not exists sf_talent_ws_idx on public.sf_talent(workspace_id, kind, updated_at desc);

create table if not exists public.sf_talent_versions (
  id            uuid primary key default gen_random_uuid(),
  talent_id     uuid not null references public.sf_talent(id) on delete cascade,
  version       int not null check (version >= 1),
  status        text not null default 'draft' check (status in ('draft','published','superseded')),
  spec          jsonb not null,
  spec_hash     text not null check (spec_hash ~ '^[0-9a-f]{64}$'),
  change_note   text not null default '',
  created_by    uuid not null references auth.users(id),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  published_at  timestamptz,
  unique (talent_id, version)
);
create index if not exists sf_talent_versions_idx on public.sf_talent_versions(talent_id, version desc);

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_talent_updated_at') then
    create trigger sf_talent_updated_at before update on public.sf_talent for each row execute function public.sf_set_updated_at(); end if;
  if not exists (select 1 from pg_trigger where tgname = 'sf_talent_versions_updated_at') then
    create trigger sf_talent_versions_updated_at before update on public.sf_talent_versions for each row execute function public.sf_set_updated_at(); end if;
end $$;

create or replace function public.sf_talent_versions_guard() returns trigger
language plpgsql set search_path = public as $$
declare in_rpc boolean := coalesce(current_setting('sf.rpc', true), '') = '1';
begin
  if old.status <> 'draft' and (new.spec is distinct from old.spec or new.spec_hash is distinct from old.spec_hash) then
    raise exception 'sf_talent_versions: version % is % and immutable (create a new draft version)', old.version, old.status
      using errcode = 'check_violation';
  end if;
  if new.talent_id <> old.talent_id or new.version <> old.version then
    raise exception 'sf_talent_versions: talent_id/version cannot change' using errcode = 'check_violation';
  end if;
  if (new.status <> old.status or new.published_at is distinct from old.published_at) and not in_rpc then
    raise exception 'sf_talent_versions: status changes only through sf_publish_talent_version' using errcode = 'check_violation';
  end if;
  return new;
end $$;
do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_talent_versions_guard') then
    create trigger sf_talent_versions_guard before update on public.sf_talent_versions for each row execute function public.sf_talent_versions_guard(); end if;
end $$;

alter table public.sf_talent          enable row level security;
alter table public.sf_talent_versions enable row level security;

do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_talent' and policyname='sf_talent_select') then execute $p$
  create policy sf_talent_select on public.sf_talent for select to authenticated using (public.sf_is_member(workspace_id)) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_talent' and policyname='sf_talent_insert') then execute $p$
  create policy sf_talent_insert on public.sf_talent for insert to authenticated
  with check (public.sf_has_role(workspace_id, array['author','admin']) and owner_id = auth.uid()) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_talent' and policyname='sf_talent_update') then execute $p$
  create policy sf_talent_update on public.sf_talent for update to authenticated
  using (public.sf_has_role(workspace_id, array['author','admin'])) with check (public.sf_has_role(workspace_id, array['author','admin'])) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_talent' and policyname='sf_talent_delete') then execute $p$
  create policy sf_talent_delete on public.sf_talent for delete to authenticated using (public.sf_has_role(workspace_id, array['admin'])) $p$; end if; end $$;

do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_talent_versions' and policyname='sf_talent_versions_select') then execute $p$
  create policy sf_talent_versions_select on public.sf_talent_versions for select to authenticated
  using (exists (select 1 from public.sf_talent t where t.id = talent_id and public.sf_is_member(t.workspace_id))) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_talent_versions' and policyname='sf_talent_versions_insert') then execute $p$
  create policy sf_talent_versions_insert on public.sf_talent_versions for insert to authenticated
  with check (created_by = auth.uid() and status = 'draft'
              and exists (select 1 from public.sf_talent t where t.id = talent_id and public.sf_has_role(t.workspace_id, array['author','admin']))) $p$; end if; end $$;
do $$ begin if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_talent_versions' and policyname='sf_talent_versions_update') then execute $p$
  create policy sf_talent_versions_update on public.sf_talent_versions for update to authenticated
  using (exists (select 1 from public.sf_talent t where t.id = talent_id and public.sf_has_role(t.workspace_id, array['author','admin'])))
  with check (exists (select 1 from public.sf_talent t where t.id = talent_id and public.sf_has_role(t.workspace_id, array['author','admin']))) $p$; end if; end $$;

grant select, insert, update, delete on public.sf_talent, public.sf_talent_versions to authenticated;

create or replace function public.sf_publish_talent_version(p_version uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare v record;
begin
  select tv.*, t.workspace_id, t.id as tid, t.kind into v
    from public.sf_talent_versions tv join public.sf_talent t on t.id = tv.talent_id where tv.id = p_version;
  if v is null then raise exception 'talent version not found' using errcode = 'no_data_found'; end if;
  if not public.sf_has_role(v.workspace_id, array['reviewer','admin']) then
    raise exception 'reviewers or admins only' using errcode = 'insufficient_privilege';
  end if;
  if v.status <> 'draft' then raise exception 'version is % and cannot be published', v.status using errcode = 'check_violation'; end if;
  perform set_config('sf.rpc', '1', true);
  update public.sf_talent_versions set status = 'superseded' where talent_id = v.tid and status = 'published';
  update public.sf_talent_versions set status = 'published', published_at = now() where id = p_version;
  update public.sf_talent set status = 'published' where id = v.tid;
  perform set_config('sf.rpc', '', true);
  insert into public.sf_audit_events (workspace_id, actor_id, actor_kind, action, entity_type, entity_id, details)
  values (v.workspace_id, auth.uid(), 'user', v.kind || '.publish', v.kind || '_version', p_version::text,
          jsonb_build_object('version', v.version, 'spec_hash', v.spec_hash));
  return jsonb_build_object('version_id', p_version, 'version', v.version, 'status', 'published');
end $$;
grant execute on function public.sf_publish_talent_version(uuid) to authenticated;
