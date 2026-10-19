-- Deliberately unsafe: proves the Skills Factory PR gate fails a PR that adds a table without row-level security.
-- This PR is closed without merging.
create table if not exists public.sf_gate_failure_proof (id uuid primary key default gen_random_uuid(), note text);
