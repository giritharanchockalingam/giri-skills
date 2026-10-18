"""Tests for build/multi-tenant-saas-patterns/scripts/rbac_to_sql.py."""
from __future__ import annotations

import re

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/multi-tenant-saas-patterns/scripts/rbac_to_sql.py"
MATRIX = REPO_ROOT / "skills/build/multi-tenant-saas-patterns/assets/rbac-matrix.csv"


def run(tmp_path, matrix, *extra):
    out = tmp_path / "policies.sql"
    r = run_script(SCRIPT, str(matrix), "--out", str(out), *extra)
    return r, out.read_text(encoding="utf-8") if out.exists() else ""


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_starter_matrix_generates_policies(tmp_path):
    r, sql = run(tmp_path, MATRIX)
    assert r.returncode == 0, r.stderr
    n = sql.count("create policy ")
    assert n == 55 and f"{n} policies" in r.stdout
    # one policy per action x role, tenant + role from JWT app_metadata
    assert "create policy projects_select_tenant_viewer on public.projects\n  for select to authenticated\n  using (tenant_id = (select (auth.jwt() -> 'app_metadata' ->> 'tenant_id'))::uuid and (select auth.jwt() -> 'app_metadata' ->> 'role') = 'viewer');" in sql
    assert "projects_select_tenant_member" in sql and "projects_select_tenant_admin" in sql and "projects_select_tenant_owner" in sql
    # own -> owner column predicate; insert -> with check; update -> using + with check; tenants table uses id
    assert re.search(r"projects_update_own_or_admin_member.*?created_by = \(select auth\.uid\(\)\)", sql, re.S)
    assert "create policy projects_insert_member_member on public.projects\n  for insert to authenticated\n  with check (" in sql
    assert re.search(r"tenants_update_admin_admin on public\.tenants\n  for update to authenticated\n  using \(id = .*?\n  with check \(id = ", sql)
    # deny cells produce nothing; service-only rows become comments; rollback block present
    assert "tenants_delete_owner_viewer" not in sql
    assert "-- billing.change_plan: no RLS policy (n/a (webhook/service only))" in sql
    assert "-- rollback:" in sql and "-- drop policy if exists projects_select_tenant_viewer on public.projects;" in sql


def test_custom_schema_and_owner_column(tmp_path):
    m = tmp_path / "m.csv"
    m.write_text("action,resource,viewer,editor,enforcement_rls\n"
                 "doc.read,docs,allow,allow,\n"
                 "doc.update,docs,deny,own,\n"
                 "doc.frobnicate,docs,allow,allow,\n", encoding="utf-8")
    r, sql = run(tmp_path, m, "--schema", "app", "--owner-column", "owner_id")
    assert r.returncode == 0, r.stderr
    assert "create policy docs_select_viewer on app.docs" in sql and "create policy docs_select_editor on app.docs" in sql
    assert "create policy docs_update_editor on app.docs" in sql and "owner_id = (select auth.uid())" in sql
    assert "-- doc.frobnicate: verb not mapped" in sql and "unmapped verbs: ['doc.frobnicate']" in r.stderr
    assert sql.count("create policy ") == 3


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.csv")[0].returncode == 1
    bad = tmp_path / "bad.csv"
    bad.write_text("name,value\na,b\n", encoding="utf-8")
    r, _ = run(tmp_path, bad)
    assert r.returncode == 1 and "lacks column" in r.stderr
    deny = tmp_path / "deny.csv"
    deny.write_text("action,resource,viewer\ndoc.read,docs,deny\n", encoding="utf-8")
    assert run(tmp_path, deny)[0].returncode == 1
