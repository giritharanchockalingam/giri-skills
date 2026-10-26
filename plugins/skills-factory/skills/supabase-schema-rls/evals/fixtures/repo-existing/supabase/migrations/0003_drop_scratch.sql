-- 0003_drop_scratch.sql (fictional eval fixture) — new, not yet applied: retire the unprotected scratch table.
-- rollback: create table public.scratch_imports (id uuid primary key, payload jsonb); -- data is not restored
drop table if exists public.scratch_imports;
