"""Tests for build/multi-tenant-saas-patterns/scripts/tenancy_audit.py."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/multi-tenant-saas-patterns/scripts/tenancy_audit.py"
SK = REPO_ROOT / "skills/build/multi-tenant-saas-patterns"
FX = SK / "evals/fixtures"


def run(tmp_path, migrations, *extra):
    out, rep = tmp_path / "audit.csv", tmp_path / "audit.md"
    r = run_script(SCRIPT, "--migrations", str(migrations), *extra, "--out", str(out), "--report", str(rep))
    rows = {x["table"]: x for x in csv.DictReader(out.open(encoding="utf-8"))} if out.exists() else None
    return r, rows, rep


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_clean_migrations_pass(tmp_path):
    r, rows, rep = run(tmp_path, FX / "migrations-clean")
    assert r.returncode == 0, r.stderr
    inv = rows["invoices"]
    assert (inv["has_tenant_id"], inv["rls_enabled"], inv["tenant_index"], inv["policies"], inv["status"]) == ("true", "true", "true", "2", "ok")
    plans = rows["plans"]
    assert plans["exempt"] == "true" and plans["status"] == "ok" and plans["has_tenant_id"] == "false"
    assert "Gate: PASS" in rep.read_text(encoding="utf-8")


def test_bad_migrations_fail(tmp_path):
    r, rows, rep = run(tmp_path, FX / "migrations-bad")
    assert r.returncode == 1
    assert rows["notes"]["findings"] == "missing tenant_id; RLS not enabled; no index leading with tenant_id"
    assert rows["attachments"]["findings"] == "RLS not enabled; no index leading with tenant_id"
    assert rows["attachments"]["has_tenant_id"] == "true"
    assert "gate: FAIL" in r.stderr and "Gate: FAIL" in rep.read_text(encoding="utf-8")


def test_reference_schema_is_clean(tmp_path):
    # the skill's own reference DDL: tenant_members' PK leads with tenant_id; profiles/tenants exempt
    r, rows, _ = run(tmp_path, SK / "assets/tenancy-schema.sql")
    assert r.returncode == 0, r.stderr
    assert rows["tenant_members"]["tenant_index"] == "true" and rows["tenant_members"]["status"] == "ok"
    assert rows["tenants"]["exempt"] == "true" and rows["profiles"]["exempt"] == "true"


def test_exempt_override_and_rls_without_policy(tmp_path):
    mig = tmp_path / "m"
    mig.mkdir()
    (mig / "0001.sql").write_text(
        "create table public.settings (id uuid primary key, tenant_id uuid not null);\n"
        "create unique index settings_tenant_uq on public.settings (tenant_id);\n"
        "alter table public.settings enable row level security;\n", encoding="utf-8")
    r, rows, _ = run(tmp_path, mig)
    assert r.returncode == 1 and "RLS enabled but no policy" in rows["settings"]["findings"]
    (mig / "0002.sql").write_text("create policy p on public.settings for select using (true);\n", encoding="utf-8")
    r, rows, _ = run(tmp_path, mig)
    assert r.returncode == 0 and rows["settings"]["policies"] == "1"
    r, rows, _ = run(tmp_path, FX / "migrations-bad", "--exempt", "notes,attachments")
    assert r.returncode == 1 and rows["notes"]["findings"] == "RLS not enabled"   # exemption keeps the RLS rule


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing")[0].returncode == 1
    empty = tmp_path / "empty"
    empty.mkdir()
    assert run(tmp_path, empty)[0].returncode == 1
    (empty / "0001.sql").write_text("-- nothing here\nselect 1;\n", encoding="utf-8")
    assert run(tmp_path, empty)[0].returncode == 1
