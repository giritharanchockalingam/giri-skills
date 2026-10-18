"""Tests for build/nextjs-enterprise-conventions/scripts/lint_conventions.py."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/nextjs-enterprise-conventions/scripts/lint_conventions.py"
FX = REPO_ROOT / "skills/build/nextjs-enterprise-conventions/evals/fixtures"


def run(tmp_path, target):
    f, r = tmp_path / "findings.csv", tmp_path / "report.md"
    res = run_script(SCRIPT, "--target", str(target), "--findings", str(f), "--report", str(r))
    rows = list(csv.DictReader(f.open(encoding="utf-8"))) if f.exists() else None
    return res, rows, r


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_violations_found_and_gate_fails(tmp_path):
    res, rows, report = run(tmp_path, FX / "repo-violations")
    assert res.returncode == 1
    assert "gate: FAIL" in res.stderr
    by_rule = {}
    for r in rows:
        by_rule.setdefault(r["rule"], []).append(r)
    assert "NX1" in by_rule and "NX2" in by_rule and "NX3" in by_rule
    assert by_rule["NX3"][0]["file"] == "server/actions/create-invoice.ts"
    assert by_rule["NX3"][0]["line"] == "5" and "createInvoiceAction" in by_rule["NX3"][0]["snippet"]
    assert by_rule["NX2"][0]["severity"] == "medium"
    assert all(r["file"] != "server/services/invoice-service.ts" for r in rows)   # the clean file
    text = report.read_text(encoding="utf-8")
    assert "Gate: FAIL" in text and "## Findings" in text and "## Rules" in text


def test_clean_repo_passes(tmp_path):
    res, rows, report = run(tmp_path, FX / "repo-clean")
    assert res.returncode == 0, res.stderr
    assert rows == []
    assert "Gate: PASS" in report.read_text(encoding="utf-8")


def test_service_role_and_raw_sql_rules(tmp_path):
    repo = tmp_path / "repo"
    (repo / "lib" / "db").mkdir(parents=True)
    (repo / "lib" / "supabase").mkdir(parents=True)
    (repo / "app").mkdir()
    (repo / "lib/db/invoices.ts").write_text("export const q = sql`select 1`;\n", encoding="utf-8")   # allowed
    (repo / "lib/supabase/server.ts").write_text("const k = process.env.SUPABASE_SERVICE_ROLE_KEY;\n", encoding="utf-8")  # allowed
    (repo / "app/util.ts").write_text("const k = process.env.SUPABASE_SERVICE_ROLE_KEY;\nconst q = sql`select 1`;\n", encoding="utf-8")
    res, rows, _ = run(tmp_path, repo)
    assert res.returncode == 1
    assert sorted((r["rule"], r["file"]) for r in rows) == [("NX4", "app/util.ts"), ("NX5", "app/util.ts")]


def test_quiet_and_bad_input(tmp_path):
    res = run_script(SCRIPT, "--target", str(FX / "repo-clean"), "--findings", str(tmp_path / "f.csv"),
                     "--report", str(tmp_path / "r.md"), "--quiet")
    assert res.returncode == 0 and res.stdout.count("\n") == 1
    assert run_script(SCRIPT, "--target", str(tmp_path / "missing")).returncode == 1
    empty = tmp_path / "empty"
    empty.mkdir()
    assert run_script(SCRIPT, "--target", str(empty), "--findings", str(tmp_path / "f.csv"), "--report", str(tmp_path / "r.md")).returncode == 1
