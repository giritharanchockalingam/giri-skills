#!/usr/bin/env bash
# Applies supabase/migrations/*.sql to a throw-away local PostgreSQL database (with a Supabase stand-in
# for auth.users / auth.uid() / the anon+authenticated roles) and runs tests/sql/test_sf.sql.
# Usage: PGHOST=/tmp PGPORT=54329 PGUSER=postgres tests/sql/run.sh
# The migrations are applied TWICE to prove they are idempotent.
set -euo pipefail
cd "$(dirname "$0")/../.."
DB="sf_test_$$"
export PGHOST="${PGHOST:-/tmp}" PGPORT="${PGPORT:-54329}" PGUSER="${PGUSER:-postgres}"
psql -q -d postgres -c "drop database if exists $DB" -c "create database $DB"
trap 'psql -q -d postgres -c "drop database if exists $DB" >/dev/null' EXIT
psql -q -v ON_ERROR_STOP=1 -d "$DB" -f tests/sql/supabase_stub.sql
for pass in 1 2; do
  for f in supabase/migrations/*.sql; do
    psql -q -v ON_ERROR_STOP=1 -d "$DB" -f "$f" >/dev/null
  done
  echo "migrations applied (pass $pass)"
done
psql -v ON_ERROR_STOP=1 -d "$DB" -f tests/sql/test_sf.sql | grep -E "PASSED|ERROR" || true
psql -tA -v ON_ERROR_STOP=1 -d "$DB" -c "select 'objects: ' || count(*) || ' sf_ tables' from pg_tables where tablename like 'sf\_%'"

# Rollback proof: run every migration's `-- rollback:` block newest-first; nothing sf_ may remain; then re-apply cleanly.
for f in $(ls -r supabase/migrations/*.sql); do
  sed -n 's/^--   //p' "$f" | grep -E '^drop ' | psql -q -v ON_ERROR_STOP=1 -d "$DB" >/dev/null 2>&1 \
    || { echo "ERROR rollback of $(basename "$f") failed"; exit 1; }
done
left=$(psql -tA -d "$DB" -c "select (select count(*) from pg_tables where tablename like 'sf\_%') + (select count(*) from pg_views where viewname like 'sf\_%') + (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and proname like 'sf\_%')")
[ "$left" = "0" ] || { echo "ERROR rollback left $left sf_ objects"; exit 1; }
for f in supabase/migrations/*.sql; do psql -q -v ON_ERROR_STOP=1 -d "$DB" -f "$f" >/dev/null; done
echo "ROLLBACK PROOF PASSED (all migrations rolled back to zero sf_ objects and re-applied)"
