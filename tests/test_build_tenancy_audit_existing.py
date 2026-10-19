"""Brownfield ("existing") path of build/multi-tenant-saas-patterns: migration history replay + RBAC coverage."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/multi-tenant-saas-patterns"
AUDIT = SK / "scripts/tenancy_audit.py"
RBAC = SK / "scripts/rbac_to_sql.py"
FX = SK / "evals/fixtures"


def run(tmp_path, migrations, *extra):
    out, rep = tmp_path / "audit.csv", tmp_path / "audit.md"
    r = run_script(AUDIT, "--migrations", str(migrations), *extra, "--out", str(out), "--report", str(rep))
    rows = {x["table"]: x for x in csv.DictReader(out.open(encoding="utf-8"))} if out.exists() else None
    return r, rows, (rep.read_text(encoding="utf-8") if rep.exists() else "")


def mig(tmp_path, files: dict):
    d = tmp_path / "migrations"
    d.mkdir()
    for name, sql in files.items():
        (d / name).write_text(sql, encoding="utf-8")
    return d


def test_existing_history_is_replayed(tmp_path):
    r, rows, md = run(tmp_path, FX / "migrations-existing", "--rbac", str(FX / "rbac-existing.csv"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert set(rows) == {"projects", "tenant_members", "tenants"}          # project_exports dropped in 0003
    p = rows["projects"]
    assert (p["has_tenant_id"], p["tenant_index"], p["policies"], p["changed_in"]) == ("true", "true", "2", "0002_tenancy.sql")
    assert rows["tenant_members"]["tenant_index"] == "true"                 # alter table … add constraint … primary key
    assert "## Altered by later migrations" in md
    assert "`tasks` is in the matrix but no migration creates it" in md


def test_later_tenant_column_needed_without_alter(tmp_path):
    d = mig(tmp_path, {"0001_a.sql": "create table public.notes (id uuid primary key, body text);\n"
                                     "alter table public.notes enable row level security;\n"
                                     "create policy n on public.notes for select using (true);\n"})
    r, rows, _ = run(tmp_path, d)
    assert r.returncode == 1 and "missing tenant_id" in rows["notes"]["findings"]


def test_drop_then_recreate_audits_the_new_table(tmp_path):
    d = mig(tmp_path, {
        "0001.sql": "create table public.items (id uuid primary key);\n",
        "0002.sql": "drop table public.items;\n"
                    "create table public.items (id uuid, tenant_id uuid not null, primary key (tenant_id, id));\n"
                    "alter table public.items enable row level security;\n"
                    "create policy i on public.items for select using (tenant_id = app.tenant_id());\n"})
    r, rows, _ = run(tmp_path, d)
    assert r.returncode == 0, r.stdout
    assert rows["items"]["file"] == "0002.sql" and rows["items"]["status"] == "ok"


def test_drop_multiple_tables_in_one_statement(tmp_path):
    d = mig(tmp_path, {
        "0001.sql": "create table public.a (id uuid primary key);\ncreate table public.b (id uuid primary key);\n"
                    "create table public.tenants (id uuid primary key);\n"
                    "alter table public.tenants enable row level security;\n"
                    "create policy t on public.tenants for select using (true);\n",
        "0002.sql": "drop table if exists public.a, public.b;\n"})
    r, rows, _ = run(tmp_path, d)
    assert set(rows) == {"tenants"} and r.returncode == 0


def test_rbac_tables_without_matrix_rows(tmp_path):
    matrix = tmp_path / "m.csv"
    matrix.write_text("action,resource,member\ntenant.read,tenants,allow\n", encoding="utf-8")
    r, rows, md = run(tmp_path, FX / "migrations-clean", "--rbac", str(matrix))
    assert r.returncode == 0
    assert "`invoices` is tenant-scoped but no matrix row covers it" in md


def test_rbac_missing_file_or_column_fails(tmp_path):
    r, _, _ = run(tmp_path, FX / "migrations-clean", "--rbac", str(tmp_path / "nope.csv"))
    assert r.returncode == 1 and "rbac matrix not found" in r.stderr
    bad = tmp_path / "bad.csv"
    bad.write_text("action,table\nx.read,y\n", encoding="utf-8")
    r, _, _ = run(tmp_path, FX / "migrations-clean", "--rbac", str(bad))
    assert r.returncode == 1 and "no 'resource' column" in r.stderr


def test_rbac_to_sql_ignores_comment_rows(tmp_path):
    out = tmp_path / "p.sql"
    r = run_script(RBAC, str(FX / "rbac-existing.csv"), "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert "for 6 action(s)" in r.stdout
    assert "fictional" not in out.read_text(encoding="utf-8").split("\n", 1)[1]
