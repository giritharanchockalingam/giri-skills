"""Brownfield ("existing") path of build/nextjs-enterprise-conventions: --baseline (recorded debt)."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/nextjs-enterprise-conventions"
SCRIPT = SK / "scripts/lint_conventions.py"
FX = SK / "evals/fixtures"


def lint(tmp_path, target, *extra):
    f, r = tmp_path / "findings.csv", tmp_path / "report.md"
    res = run_script(SCRIPT, "--target", str(target), *extra, "--findings", str(f), "--report", str(r))
    rows = list(csv.DictReader(f.open(encoding="utf-8"))) if f.exists() else []
    return res, rows, (r.read_text(encoding="utf-8") if r.exists() else "")


def test_known_debt_does_not_gate_and_resolved_listed(tmp_path):
    res, rows, md = lint(tmp_path, FX / "repo-violations", "--baseline", str(FX / "baseline-findings.csv"))
    assert res.returncode == 0, res.stderr
    assert {(r["rule"], r["status"]) for r in rows} == {("NX2", "new"), ("NX1", "known"), ("NX3", "known")}
    assert "1 new, 3 known from the baseline, 1 resolved" in md
    assert "- NX5 `app/reports/page.tsx`" in md


def test_new_high_finding_still_fails_with_baseline(tmp_path):
    base = tmp_path / "base.csv"
    base.write_text("rule,file,line,snippet,severity\nNX2,app/dashboard/page.tsx,3,"
                    "\"console.log(\"\"rendering dashboard\"\");\",medium\n", encoding="utf-8")
    res, rows, md = lint(tmp_path, FX / "repo-violations", "--baseline", str(base))
    assert res.returncode == 1 and "3 new high-severity" in res.stderr
    assert "Gate: FAIL (new high-severity findings)" in md


def test_line_moves_still_match(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    page = repo / "app/page.tsx"
    page.write_text('console.log("x");\n', encoding="utf-8")
    first = tmp_path / "first"
    first.mkdir()
    lint(first, repo)
    page.write_text('// moved\n// down\nconsole.log("x");\n', encoding="utf-8")
    res, rows, _ = lint(tmp_path, repo, "--baseline", str(first / "findings.csv"))
    assert rows[0]["line"] == "3" and rows[0]["status"] == "known"


def test_duplicate_snippets_match_one_to_one(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app/page.tsx").write_text('console.log("x");\nconsole.log("x");\n', encoding="utf-8")
    base = tmp_path / "base.csv"
    base.write_text('rule,file,line,snippet,severity\nNX2,app/page.tsx,1,"console.log(""x"");",medium\n', encoding="utf-8")
    _, rows, _ = lint(tmp_path, repo, "--baseline", str(base))
    assert sorted(r["status"] for r in rows) == ["known", "new"]


def test_without_baseline_everything_is_new(tmp_path):
    res, rows, md = lint(tmp_path, FX / "repo-violations")
    assert res.returncode == 1 and all(r["status"] == "new" for r in rows)
    assert "## Baseline" not in md


def test_bad_baseline_fails(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    res, _, _ = lint(tmp_path, FX / "repo-clean", "--baseline", str(bad))
    assert res.returncode == 1 and "baseline lacks column" in res.stderr
    res, _, _ = lint(tmp_path, FX / "repo-clean", "--baseline", str(tmp_path / "none.csv"))
    assert res.returncode == 1 and "baseline not found" in res.stderr
