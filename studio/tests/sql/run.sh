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
