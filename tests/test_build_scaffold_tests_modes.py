"""Brownfield ("existing") path of build/test-strategy-tdd: kept test files are matched to the criteria."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/test-strategy-tdd"
SCRIPT = SK / "scripts/scaffold_tests.py"
SEED = SK / "scripts/seed_repo.py"
FEATURE = SK / "evals/fixtures/feature.md"
SUITE = SK / "evals/fixtures/repo-existing-suite"
FILES = "server/services/export-service.ts,server/actions/request-export.ts"


def scaffold(tmp_path, repo, *extra, feature=FEATURE, files=FILES):
    rep, plan = tmp_path / "r.json", tmp_path / "p.md"
    res = run_script(SCRIPT, str(feature), "--files", files, "--target", str(repo), *extra,
                     "--report", str(rep), "--plan", str(plan))
    return res, json.loads(rep.read_text(encoding="utf-8")), plan.read_text(encoding="utf-8")


def test_existing_suite_is_read_and_gaps_listed(tmp_path):
    repo = tmp_path / "repo"
    assert run_script(SEED, "--from", str(SUITE), "--target", str(repo)).returncode == 0
    kept = repo / "tests/unit/server-services-export-service.test.ts"
    before = kept.read_text(encoding="utf-8")
    res, data, plan = scaffold(tmp_path, repo)
    assert res.returncode == 0, res.stderr
    assert kept.read_text(encoding="utf-8") == before
    assert data["written"] == ["tests/unit/server-actions-request-export.test.ts"]
    (e,) = data["existing_tests"]
    assert e["titles"] == ["builds the CSV header row", "export contains only the caller's tenant rows"]
    assert e["criteria_covered"] == [3] and e["criteria_missing"] == [1, 2]
    assert "## Existing tests (kept — add the missing criteria by hand)" in plan
    assert "#1 An admin can request a CSV export of the tenant's invoices" in plan


def test_todo_and_fixme_titles_count_as_coverage(tmp_path):
    repo = tmp_path / "repo"
    t = repo / "tests/unit/server-services-export-service.test.ts"
    t.parent.mkdir(parents=True)
    t.write_text('it.todo("An admin can request a CSV export of the tenant invoices");\n'
                 "test.fixme('member without admin role gets not allowed and an audit entry is written', () => {});\n",
                 encoding="utf-8")
    _, data, _ = scaffold(tmp_path, repo, files="server/services/export-service.ts")
    (e,) = data["existing_tests"]
    assert e["criteria_covered"] == [1, 2] and e["criteria_missing"] == [3]


def test_unrelated_titles_cover_nothing(tmp_path):
    repo = tmp_path / "repo"
    t = repo / "tests/unit/server-services-export-service.test.ts"
    t.parent.mkdir(parents=True)
    t.write_text('it("keeps the header", () => {});\n', encoding="utf-8")
    _, data, plan = scaffold(tmp_path, repo, files="server/services/export-service.ts")
    assert data["existing_tests"][0]["criteria_covered"] == []
    assert "| none |" in plan or "| 1 | none |" in plan


def test_fresh_repo_has_no_existing_tests_section(tmp_path):
    _, data, plan = scaffold(tmp_path, tmp_path / "fresh")
    assert data["existing_tests"] == [] and "## Existing tests" not in plan
