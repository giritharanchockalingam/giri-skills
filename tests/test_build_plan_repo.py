"""Brownfield ("existing") path of build/spec-to-plan: --repo file lookup and migration checks."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/spec-to-plan"
SCRIPT = SK / "scripts/plan.py"
FX = SK / "evals/fixtures"


def plan(tmp_path, spec, section, *extra):
    out, tasks = tmp_path / "plan.md", tmp_path / "tasks.csv"
    r = run_script(SCRIPT, str(spec), "--section", section, *extra, "--out", str(out), "--tasks", str(tasks))
    rows = list(csv.DictReader(tasks.open(encoding="utf-8"))) if tasks.exists() else []
    return r, rows, (out.read_text(encoding="utf-8") if out.exists() else "")


def spec_file(tmp_path, body):
    p = tmp_path / "SPEC.md"
    p.write_text("# SPEC\n\n## Feature\n" + body, encoding="utf-8")
    return p


def test_fixture_repo_marks_files_and_flags_collision(tmp_path):
    r, rows, md = plan(tmp_path, FX / "SPEC.md", "Invoice export", "--repo", str(FX / "repo-existing"))
    assert r.returncode == 0, r.stderr
    by = {t["id"]: t["repo_check"] for t in rows}
    assert by["T1"] == "supabase/migrations/0007_export_jobs.sql: create"
    assert by["T2"] == "no files named"
    assert by["T4"] == "app/(app)/invoices/page.tsx: modify"
    assert "## Repo check" in md and "(0007) — renumber it after it" in md
    assert "1 repo problem(s)" in r.stdout


def test_editing_an_existing_migration_is_flagged(tmp_path):
    repo = tmp_path / "repo"
    (repo / "supabase/migrations").mkdir(parents=True)
    (repo / "supabase/migrations/0003_x.sql").write_text("select 1;", encoding="utf-8")
    spec = spec_file(tmp_path, "- Change x\n  - files: supabase/migrations/0003_x.sql\n")
    _, _, md = plan(tmp_path, spec, "Feature", "--repo", str(repo))
    assert "is an existing migration — never edit an applied one" in md


def test_well_numbered_new_migration_has_no_problem(tmp_path):
    repo = tmp_path / "repo"
    (repo / "supabase/migrations").mkdir(parents=True)
    (repo / "supabase/migrations/0003_x.sql").write_text("select 1;", encoding="utf-8")
    spec = spec_file(tmp_path, "- Add y\n  - files: supabase/migrations/0004_y.sql, `lib/db/y.ts`\n")
    _, rows, md = plan(tmp_path, spec, "Feature", "--repo", str(repo))
    assert rows[0]["repo_check"] == "supabase/migrations/0004_y.sql: create; lib/db/y.ts: create"
    assert "No problems found." in md


def test_without_repo_no_check_section(tmp_path):
    r, rows, md = plan(tmp_path, FX / "SPEC.md", "Invoice export")
    assert r.returncode == 0 and "## Repo check" not in md
    assert all(t["repo_check"] == "" for t in rows)


def test_missing_repo_dir_fails(tmp_path):
    r, _, _ = plan(tmp_path, FX / "SPEC.md", "Invoice export", "--repo", str(tmp_path / "nope"))
    assert r.returncode == 1 and "repo not found" in r.stderr
