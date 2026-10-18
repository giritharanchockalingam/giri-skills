"""Tests for build/spec-to-plan/scripts/plan.py."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/spec-to-plan/scripts/plan.py"
SK = REPO_ROOT / "skills/build/spec-to-plan"
SPEC = SK / "evals/fixtures/SPEC.md"
TMPL = SK / "assets/plan-template.md"
TBD = "[TO BE BASELINED — owner: Tech lead]"


def run(tmp_path, spec, section, *extra):
    plan, tasks = tmp_path / "plan.md", tmp_path / "tasks.csv"
    r = run_script(SCRIPT, str(spec), "--section", section, "--template", str(TMPL), "--out", str(plan), "--tasks", str(tasks), *extra)
    rows = list(csv.DictReader(tasks.open(encoding="utf-8"))) if tasks.exists() else None
    return r, plan, rows


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_section_to_plan(tmp_path):
    r, plan, rows = run(tmp_path, SPEC, "Invoice export")
    assert r.returncode == 0, r.stderr
    assert [x["id"] for x in rows] == ["T1", "T2", "T3", "T4"]
    t1, t2, t3, t4 = rows
    assert t1["files"] == "supabase/migrations/0007_export_jobs.sql" and t1["size"] == "S"
    assert t1["test"].startswith("tests/integration/rls/export_jobs.test.ts")
    assert t2["task"] == "Export service builds the CSV"                       # inline fields stripped
    assert t2["acceptance"].startswith("Returns CSV with header") and t2["rollback"] == "revert commit"
    assert t2["files"] == TBD
    assert t3["test"] == "tests/unit/request-export.test.ts"                   # `tests:` key
    assert t4["acceptance"] == TBD and t4["rollback"] == "flag off"
    text = plan.read_text(encoding="utf-8")
    assert text.startswith("# Plan — invoice-export — ")
    assert "| Source | SPEC §Invoice export |" in text and "| Size | SMMM (4 tasks) |" in text
    assert "### T3 — Server action `requestExport` with zod + requireRole(admin) (M)" in text
    assert "## Gates" in text and "| approve | plan posted |" in text
    assert "## Rollback (whole feature)" in text and "- T1: down-migration drops export_jobs" in text
    assert "### T1 — <name> (S)" not in text


def test_thin_section_marks_tbd(tmp_path):
    r, plan, rows = run(tmp_path, SPEC, "Audit log", "--slug", "audit")
    assert r.returncode == 0, r.stderr
    assert len(rows) == 2 and all(x["test"] == TBD and x["rollback"] == TBD for x in rows)
    assert "8 field(s) to be baselined" in r.stdout
    assert plan.read_text(encoding="utf-8").startswith("# Plan — audit — ")


def test_split_warning_over_8_tasks(tmp_path):
    spec = tmp_path / "SPEC.md"
    spec.write_text("# S\n\n## Big\n" + "".join(f"- task {i}\n" for i in range(9)) + "\n## Other\n- x\n", encoding="utf-8")
    r, plan, rows = run(tmp_path, spec, "Big")
    assert r.returncode == 0 and len(rows) == 9
    assert "Split warning" in plan.read_text(encoding="utf-8")


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.md", "x")[0].returncode == 1
    r, _, _ = run(tmp_path, SPEC, "No such section")
    assert r.returncode == 1 and "section not found" in r.stderr
    r, _, _ = run(tmp_path, SPEC, "Purpose")
    assert r.returncode == 1 and "no bullet" in r.stderr
