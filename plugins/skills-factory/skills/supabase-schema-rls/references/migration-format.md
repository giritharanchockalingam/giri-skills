# Migration Format

## Naming
`supabase/migrations/<YYYYMMDDHHMMSS>_<verb>_<object>.sql` — created with `supabase migration new <verb>_<object>`. One logical change per file. Verbs: `create`, `add`, `alter`, `drop`, `backfill`, `policy`.

## File layout
```sql
-- Migration: 20260401120000_create_invoices
-- Purpose: invoices per tenant with RLS (SPEC §3.4, plan 2026-04-01-invoice-export)
-- Depends on: 0001_init (app.tenant_id(), app.has_role())
-- Destructive: no
-- Backfill: none

begin;

-- 1. Tables
create table public.invoices (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade default app.tenant_id(),
  created_by    uuid not null references auth.users(id) default auth.uid(),
  number        text not null,
  amount_cents  bigint not null check (amount_cents >= 0),
  status        text not null default 'draft' check (status in ('draft','issued','paid','void')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (tenant_id, number)
);

-- 2. Indexes (tenant_id leads)
create index invoices_tenant_created_idx on public.invoices (tenant_id, created_at desc);
create index invoices_tenant_status_idx  on public.invoices (tenant_id, status);

-- 3. Triggers
create trigger invoices_set_updated_at before update on public.invoices
  for each row execute function app.set_updated_at();

-- 4. RLS
alter table public.invoices enable row level security;
create policy invoices_select_tenant on public.invoices for select to authenticated
  using (tenant_id = (select app.tenant_id()));
create policy invoices_insert_member on public.invoices for insert to authenticated
  with check (tenant_id = (select app.tenant_id()) and (select app.has_role('member')));
create policy invoices_update_admin on public.invoices for update to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')))
  with check (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));
create policy invoices_delete_admin on public.invoices for delete to authenticated
  using (tenant_id = (select app.tenant_id()) and (select app.has_role('admin')));

-- 5. Grants (defaults are usually right; be explicit for functions)
-- 6. Audit hook
create trigger invoices_audit after insert or update or delete on public.invoices
  for each row execute function app.audit_row();

commit;

-- rollback:
-- begin;
-- drop trigger if exists invoices_audit on public.invoices;
-- drop trigger if exists invoices_set_updated_at on public.invoices;
-- drop policy if exists invoices_delete_admin on public.invoices;
-- drop policy if exists invoices_update_admin on public.invoices;
-- drop policy if exists invoices_insert_member on public.invoices;
-- drop policy if exists invoices_select_tenant on public.invoices;
-- drop index if exists invoices_tenant_status_idx;
-- drop index if exists invoices_tenant_created_idx;
-- drop table if exists public.invoices;
-- commit;
```

## Rollback block rules
| Rule | Reason |
|---|---|
| Commented `-- rollback:` block at the end; statements in reverse order | reviewer can apply it by hand; linter checks presence |
| Every forward statement has an inverse, or an explicit `-- irreversible: <reason>` line | no silent one-way migrations |
| Rollback is executed only as a new forward migration (`<ts>_revert_<name>.sql` containing the block) | history stays append-only |
| Never edit an applied migration | checksum drift breaks `db push` and teammates' local DBs |

## Expand → migrate → contract (destructive changes)
| Release | Step | Example: rename `amount` → `amount_cents` |
|---|---|---|
| N | Expand | add `amount_cents` nullable; trigger copies writes both ways; app reads old |
| N | Backfill | `update … set amount_cents = amount*100 where amount_cents is null` in batches of 5k |
| N+1 | Migrate | app reads/writes new column; old column kept |
| N+2 | Contract | drop trigger, drop old column, set not null |

Never `drop column`, `alter type` on a populated column, or `rename` in the same release that the app starts depending on the change.

## Backfill rules
- Batches (`limit 5000` loop with `pg_sleep(0.1)`), never one giant `update`.
- Separate migration file from the schema change.
- Idempotent (`where new_col is null`).
- Timeout: `set local statement_timeout = '5min'` at the top.

## Seed (`supabase/seed.sql`)
- Two tenants, one user per role in each, three rows per tenant table. Enough for every negative RLS test.
- Deterministic UUIDs (`'00000000-0000-0000-0000-00000000000a'`) so tests can reference them.
- Never production data.

## Commands
| Task | Command |
|---|---|
| New migration | `supabase migration new create_invoices` |
| Apply locally from scratch | `supabase db reset` |
| Diff local vs migrations (catch drift) | `supabase db diff -f check` → must be empty |
| Types | `supabase gen types typescript --local > lib/db/types.ts` |
| Push to linked remote | `supabase db push` (CI only; see prod.yml) |
| Lint | `python3 -I scripts/rls_lint.py supabase/migrations` |
