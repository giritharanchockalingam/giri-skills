"""Tests for build/test-strategy-tdd/scripts/scaffold_tests.py."""
from __future__ import annotations

import json
import shutil

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/test-strategy-tdd/scripts/scaffold_tests.py"
SK = REPO_ROOT / "skills/build/test-strategy-tdd"
FEATURE = SK / "evals/fixtures/feature.md"
FILES = "server/services/export-service.ts,server/actions/request-export.ts,app/(app)/invoices/page.tsx,components/features/invoices/ExportButton.tsx"


def run(tmp_path, target, files=FILES, *extra, feature=FEATURE):
    rep, plan = tmp_path / "scaffold-report.json", tmp_path / "test-plan.md"
    r = run_script(SCRIPT, str(feature), "--files", files, "--target", str(target), *extra, "--report", str(rep), "--plan", str(plan))
    data = json.loads(rep.read_text(encoding="utf-8")) if rep.exists() else None
    return r, data, plan


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_scaffold_writes_stubs(tmp_path):
    repo = tmp_path / "repo"
    r, data, plan = run(tmp_path, repo)
    assert r.returncode == 0, r.stderr
    assert data["written"] == ["tests/unit/server-services-export-service.test.ts",
                               "tests/unit/server-actions-request-export.test.ts",
                               "tests/e2e/app-app-invoices-page.spec.ts"]
    assert data["components"] == ["tests/unit/components-features-invoices-exportbutton.test.tsx"]
    unit = (repo / "tests/unit/server-services-export-service.test.ts").read_text(encoding="utf-8")
    assert unit.count("it.todo(") == 4 and 'import { describe, it, expect } from "vitest";' in unit
    assert "it.todo(\"The export contains only the caller's tenant rows\")" in unit
    assert 'from "@/server/services/export-service"' in unit
    e2e = (repo / "tests/e2e/app-app-invoices-page.spec.ts").read_text(encoding="utf-8")
    assert e2e.count("test.fixme(") == 4 and 'await page.goto("/invoices");' in e2e
    assert "\\u2014" not in unit + e2e
    types = {f["source"]: f["type"] for f in data["files"]}
    assert types["server/services/export-service.ts"] == "service" and types["app/(app)/invoices/page.tsx"] == "page / flow"
    text = plan.read_text(encoding="utf-8")
    assert "## Pyramid" in text and "## Criteria map" in text and "| 3 | The export contains only" in text
    assert "manual (component)" in text


def test_never_overwrites_existing(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(SK / "evals/fixtures/repo-existing", repo)
    before = (repo / "tests/unit/server-services-export-service.test.ts").read_text(encoding="utf-8")
    r, data, plan = run(tmp_path, repo, "server/services/export-service.ts,lib/db/export.ts")
    assert r.returncode == 0, r.stderr
    assert (repo / "tests/unit/server-services-export-service.test.ts").read_text(encoding="utf-8") == before
    assert data["skipped"] == ["tests/unit/server-services-export-service.test.ts"]
    assert data["written"] == ["tests/unit/lib-db-export.test.ts"]
    assert "exists — kept" in plan.read_text(encoding="utf-8")


def test_dry_run_writes_nothing(tmp_path):
    repo = tmp_path / "repo"
    r, data, _ = run(tmp_path, repo, FILES, "--dry-run")
    assert r.returncode == 0 and data["dry_run"] is True
    assert data["written"] == [] and len(data["would_write"]) == 3
    assert not (repo / "tests").exists()


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "repo", feature=tmp_path / "missing.md")[0].returncode == 1
    empty = tmp_path / "f.md"
    empty.write_text("# Title only\n", encoding="utf-8")
    assert run(tmp_path, tmp_path / "repo", feature=empty)[0].returncode == 1
    assert run(tmp_path, tmp_path / "repo", " , ")[0].returncode == 1


# ---------------------------------------------------------------- --tasks: the approved plan names the test files

OPS_FEATURE = ("# Ops status\n"
               "- the checker returns one status row per configured endpoint with latency\n"
               "- an alert is emitted once per transition from ok to down\n"
               "- GET /api/cron/check answers 200 and writes a run record\n"
               "- ops_status table exists with RLS\n"
               "- the status page lists every endpoint\n")
OPS_TASKS = ("id,task,acceptance,test,rollback,files,size\n"
             "T1,Checker library,the checker returns one status row per configured endpoint with latency,"
             "tests/unit/checker.test.js: returns a row per endpoint and marks timeouts down,remove lib/checker.js,lib/checker.js,S\n"
             "T2,Alert routing,an alert is emitted once per transition from ok to down,"
             "\"unit tests/unit/alerts.test.js covers the ok→down→ok transitions; also tests/unit/checker.test.js: no duplicate alert\","
             "remove lib/alerts.js,lib/alerts.js; lib/checker.js,S\n"
             "T3,Cron route,GET /api/cron/check answers 200 and writes a run record,route test asserts 200 and the record,"
             "remove the route,app/api/cron/check/route.js,S\n"
             "T4,Migration,ops_status table exists with RLS,migration integration test,drop the table,supabase/migrations/0001-ops-status.sql,S\n"
             "T5,Status page,the status page lists every endpoint,tests/e2e/status.spec.ts: lists every endpoint,remove page,app/status/page.js,S\n")
OPS_FILES = "lib/checker.js,lib/alerts.js,app/api/cron/check/route.js,supabase/migrations/0001-ops-status.sql,app/status/page.js,docs/observability.md"


def ops(tmp_path, *extra, tasks=OPS_TASKS, files=OPS_FILES):
    (tmp_path / "feature.md").write_text(OPS_FEATURE, encoding="utf-8")
    (tmp_path / "tasks.csv").write_text(tasks, encoding="utf-8")
    repo = tmp_path / "repo"
    r, data, plan = run(tmp_path, repo, files, "--tasks", str(tmp_path / "tasks.csv"), "--flavour", "js", *extra,
                        feature=tmp_path / "feature.md")
    return r, data, plan, repo


def test_tasks_csv_test_cells_name_the_stubs_with_their_own_acceptance(tmp_path):
    """The ops-status run wrote tests/unit/lib-checker.test.js with all five criteria while the approved plan named
    tests/unit/checker.test.js. With --tasks the plan's names win and each stub carries its task's acceptance only."""
    r, data, plan, repo = ops(tmp_path)
    assert r.returncode == 0, r.stderr
    assert sorted(data["written"]) == ["tests/e2e/status.spec.js", "tests/unit/alerts.test.js",
                                       "tests/unit/app-api-cron-check-route.test.js", "tests/unit/checker.test.js"]
    assert data["plan_tests"] == ["tests/e2e/status.spec.js", "tests/unit/alerts.test.js", "tests/unit/checker.test.js"]
    assert not (repo / "tests/unit/lib-checker.test.js").exists() and not (repo / "tests/unit/lib-alerts.test.js").exists()
    checker = (repo / "tests/unit/checker.test.js").read_text(encoding="utf-8")
    assert checker.count("it.todo(") == 3                                              # T1 + T2 (names this file too) + the negative case
    assert 'it.todo("the checker returns one status row per configured endpoint with latency")' in checker
    assert 'it.todo("an alert is emitted once per transition from ok to down")' in checker
    assert "GET /api/cron/check" not in checker and "ops_status table" not in checker   # other tasks' criteria stay out
    assert 'from "@/lib/checker"' in checker and 'from "@/lib/alerts"' in checker
    alerts = (repo / "tests/unit/alerts.test.js").read_text(encoding="utf-8")
    assert alerts.count("it.todo(") == 2 and "ok to down" in alerts
    by_path = {t["path"]: t for t in data["tasks"]}
    assert by_path["tests/unit/checker.test.js"]["tasks"] == ["T1", "T2"] and by_path["tests/unit/alerts.test.js"]["tasks"] == ["T2"]
    assert "3 named by the plan" in r.stdout
    assert "Test files named by the plan's `test` cells" in plan.read_text(encoding="utf-8")


def test_task_without_a_test_path_falls_back_to_per_source_naming_with_its_own_acceptance(tmp_path):
    r, data, plan, repo = ops(tmp_path)
    route = (repo / "tests/unit/app-api-cron-check-route.test.js").read_text(encoding="utf-8")   # T3 names no path
    assert route.count("it.todo(") == 2 and 'it.todo("GET /api/cron/check answers 200 and writes a run record")' in route
    row = next(f for f in data["files"] if f["source"] == "app/api/cron/check/route.js")
    assert row["criteria"] == ["GET /api/cron/check answers 200 and writes a run record"] and "plan" not in row
    text = plan.read_text(encoding="utf-8")
    assert "| 3 | GET /api/cron/check answers 200 and writes a run record | `tests/unit/app-api-cron-check-route.test.js` |" in text
    assert "| 4 | ops_status table exists with RLS | — |" in text                   # a .sql task has no stub anywhere


def test_plan_named_test_takes_the_repo_flavour_and_covers_its_page(tmp_path):
    r, data, plan, repo = ops(tmp_path)
    assert not list(repo.rglob("*.ts"))
    spec = (repo / "tests/e2e/status.spec.js").read_text(encoding="utf-8")
    assert 'await page.goto("/status");' in spec and spec.count("test.fixme(") == 2 and "lists every endpoint" in spec
    (t,) = [t for t in data["tasks"] if t["path"] == "tests/e2e/status.spec.js"]
    assert t["renamed_from"] == "tests/e2e/status.spec.ts" and t["source"] == ["app/status/page.js"]
    assert "`tests/e2e/status.spec.ts` → `tests/e2e/status.spec.js`" in plan.read_text(encoding="utf-8")
    assert not (repo / "tests/e2e/app-status-page.spec.js").exists()               # covered by the plan's spec, no twin


def test_never_a_stub_for_non_code_files_with_or_without_tasks(tmp_path):
    r, data, plan, repo = ops(tmp_path)
    assert data["non_source"] == ["supabase/migrations/0001-ops-status.sql", "docs/observability.md"]
    assert not list(repo.rglob("*sql*")) and not list(repo.rglob("*observability*"))
    sub = tmp_path / "plain"
    sub.mkdir()
    r2, d2, _ = run(sub, sub / "repo", "lib/a.js,supabase/migrations/0001-x.sql,ops/alerts.yaml,config.json,.env.local,README.md")
    assert r2.returncode == 0, r2.stderr
    assert d2["written"] == ["tests/unit/lib-a.test.js"]
    assert d2["non_source"] == ["supabase/migrations/0001-x.sql", "ops/alerts.yaml", "config.json", ".env.local", "README.md"]
    assert not list((sub / "repo").rglob("*sql*"))


def test_tasks_with_existing_plan_named_test_is_kept_and_gaps_listed(tmp_path):
    repo = tmp_path / "repo"
    (repo / "tests/unit").mkdir(parents=True)
    (repo / "tests/unit/checker.test.js").write_text('it("the checker returns one status row per configured endpoint with latency", () => {});\n', encoding="utf-8")
    r, data, plan, _ = ops(tmp_path)
    assert r.returncode == 0, r.stderr
    assert data["skipped"] == ["tests/unit/checker.test.js"] and "tests/unit/checker.test.js" not in data["written"]
    (e,) = data["existing_tests"]
    assert e["criteria_covered"] == [1] and e["criteria_missing"] == [2]           # only the criteria this stub owns


def test_tasks_file_missing_or_malformed_exits_1(tmp_path):
    (tmp_path / "feature.md").write_text(OPS_FEATURE, encoding="utf-8")
    r, _, _ = run(tmp_path, tmp_path / "repo", "lib/a.js", "--tasks", str(tmp_path / "nope.csv"), feature=tmp_path / "feature.md")
    assert r.returncode == 1 and "tasks file not found" in r.stderr
    (tmp_path / "bad.csv").write_text("id,task\nT1,x\n", encoding="utf-8")
    r, _, _ = run(tmp_path, tmp_path / "repo", "lib/a.js", "--tasks", str(tmp_path / "bad.csv"), feature=tmp_path / "feature.md")
    assert r.returncode == 1 and "tasks.csv needs" in r.stderr
