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
