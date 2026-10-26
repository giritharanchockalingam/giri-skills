# Audit Log

## Requirements
| Requirement | Default |
|---|---|
| What | every insert/update/delete on tenant data tables; every membership, role, billing, settings, flag change; auth events of interest (invite accepted, tenant switch) |
| Who | actor user id (or `system:<job>`), tenant id, `requestId` |
| Immutability | append-only: no update/delete policies; table owned by a role the app cannot alter; optional periodic export to WORM storage |
| Retention | 1 year hot (`[TO BE BASELINED — owner: ___]`), then archive to storage per compliance |
| Access | tenant admins read their tenant's log (RLS); owners export; platform operators via `security definer` function with logging |
| PII | before/after snapshots stored, but redact fields listed in `app.audit_redact_columns` (passwords never exist in tables anyway; emails kept — needed for audit) |

## Schema
```sql
create table public.audit_log (
  id          bigint generated always as identity primary key,
  ts          timestamptz not null default now(),
  tenant_id   uuid not null,
  actor_id    uuid,                         -- null for system
  actor_type  text not null default 'user' check (actor_type in ('user','system','service')),
  request_id  text,
  entity      text not null,                -- table or domain name: 'invoices', 'tenant_members', 'feature_flag'
  entity_id   text,
  action      text not null,                -- 'insert' | 'update' | 'delete' | domain verbs: 'invite.accept', 'role.change'
  before      jsonb,
  after       jsonb,
  diff        jsonb generated always as (app.jsonb_diff(before, after)) stored,
  meta        jsonb                         -- ip, user agent, reason
);
create index audit_log_tenant_ts_idx on public.audit_log (tenant_id, ts desc);
create index audit_log_entity_idx    on public.audit_log (tenant_id, entity, entity_id);

alter table public.audit_log enable row level security;
create policy audit_select_admin on public.audit_log for select to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));
-- no insert/update/delete policies for authenticated: writes happen via trigger (security definer) or service role.
revoke update, delete on public.audit_log from authenticated, anon;
```

## Row trigger (`app.audit_row()`)
```sql
create or replace function app.audit_row() returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_tenant uuid; v_before jsonb; v_after jsonb;
begin
  v_before := case when tg_op in ('UPDATE','DELETE') then to_jsonb(old) end;
  v_after  := case when tg_op in ('INSERT','UPDATE') then to_jsonb(new) end;
  v_tenant := coalesce((v_after->>'tenant_id')::uuid, (v_before->>'tenant_id')::uuid);
  insert into public.audit_log (tenant_id, actor_id, actor_type, request_id, entity, entity_id, action, before, after)
  values (
    v_tenant,
    (select auth.uid()),
    case when (select auth.uid()) is null then 'system' else 'user' end,
    current_setting('request.headers', true)::jsonb->>'x-request-id',
    tg_table_name,
    coalesce(v_after->>'id', v_before->>'id'),
    lower(tg_op), v_before, v_after);
  return coalesce(new, old);
end $$;
```
Attach `after insert or update or delete … for each row execute function app.audit_row()` to every tenant data table (template does this).

## Application events (non-row actions)
`server/services/audit.ts` → `writeAudit({ entity: 'invitation', entityId, action: 'invite.accept', after, meta })` through the admin client (`// rls-lint: allow — audit append only`). Use for: invite sent/accepted, tenant switch, export generated, flag toggled, login anomalies.

## Reading and exporting
- Admin UI: paginated by `(tenant_id, ts desc)`; filter by entity, actor, date.
- Export: owner-only server action → CSV/JSON to private storage path `${tenantId}/audit/<date>.json`; audited itself.
- Operators: `app.audit_search(p_tenant, …)` `security definer` with mandatory reason parameter, which writes its own audit row.

## Retention job
Nightly: move rows older than retention to `audit_log_archive` (or storage), delete from hot table via service role, log counts. Never from the app path.

## Tests
- Trigger: insert/update/delete on a tenant table produce 3 audit rows with correct actor/tenant/diff.
- RLS: admin of tenant A reads only A; member cannot read; nobody can update/delete.
- App event: `acceptInvite` writes `invite.accept`.
