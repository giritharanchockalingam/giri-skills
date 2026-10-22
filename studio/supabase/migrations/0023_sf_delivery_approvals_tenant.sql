-- 0023: sf_delivery_approvals carries the tenant key directly (found by the factory's own tenant-isolation gate on #125).
-- Every tenant-scoped table holds workspace_id with a tenant-leading index and a policy that reads it, rather than
-- reaching the tenant through a join. Backfilled from the run; kept in step by a trigger; RLS rewritten to use it.
-- rollback: drop trigger sf_delivery_approvals_ws on public.sf_delivery_approvals; drop function public.sf_delivery_approval_ws();
--           alter table public.sf_delivery_approvals drop column workspace_id;  (policies then need the 0022 versions back)
alter table public.sf_delivery_approvals add column if not exists workspace_id uuid references public.sf_workspaces(id) on delete cascade;
update public.sf_delivery_approvals a set workspace_id = r.workspace_id from public.sf_delivery_runs r where r.id = a.run_id and a.workspace_id is null;
alter table public.sf_delivery_approvals alter column workspace_id set not null;
create index if not exists sf_delivery_approvals_ws_idx on public.sf_delivery_approvals (workspace_id, run_id, created_at);

-- the tenant of an approval is the tenant of its run — set on insert, never trusted from the client
create or replace function public.sf_delivery_approval_ws() returns trigger language plpgsql set search_path = public as $$
begin
  select r.workspace_id into new.workspace_id from public.sf_delivery_runs r where r.id = new.run_id;
  if new.workspace_id is null then raise exception 'approval for unknown run %', new.run_id using errcode = 'foreign_key_violation'; end if;
  return new;
end $$;
do $$ begin if not exists (select 1 from pg_trigger where tgname = 'sf_delivery_approvals_ws') then
  create trigger sf_delivery_approvals_ws before insert on public.sf_delivery_approvals for each row execute function public.sf_delivery_approval_ws(); end if; end $$;

drop policy if exists sf_delivery_approvals_select on public.sf_delivery_approvals;
drop policy if exists sf_delivery_approvals_insert on public.sf_delivery_approvals;
create policy sf_delivery_approvals_select on public.sf_delivery_approvals for select to authenticated using (public.sf_is_member(workspace_id));
create policy sf_delivery_approvals_insert on public.sf_delivery_approvals for insert to authenticated
  with check (approved_by = auth.uid() and exists (select 1 from public.sf_delivery_runs r where r.id = run_id and public.sf_is_member(r.workspace_id)));
