"""Brownfield ("existing") path of build/observability-setup: seed copy and the console.* inventory."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/observability-setup"
INSTALL = SK / "scripts/install.py"
SEED = SK / "scripts/seed_repo.py"
FX = SK / "evals/fixtures/repo-existing"


def install(tmp_path, repo, *extra):
    j, m = tmp_path / "r.json", tmp_path / "r.md"
    res = run_script(INSTALL, "--target", str(repo), *extra, "--report-json", str(j), "--report-md", str(m))
    return res, json.loads(j.read_text(encoding="utf-8")), m.read_text(encoding="utf-8")


def seeded(tmp_path):
    repo = tmp_path / "repo"
    res = run_script(SEED, "--from", str(FX), "--target", str(repo))
    assert res.returncode == 0, res.stderr
    return repo


def test_existing_repo_merges_without_overwriting(tmp_path):
    repo = seeded(tmp_path)
    logger_before = (repo / "lib/logger.ts").read_text(encoding="utf-8")
    env_before = (repo / ".env.example").read_text(encoding="utf-8")
    res, data, md = install(tmp_path, repo)
    assert res.returncode == 0, res.stderr
    assert (repo / "lib/logger.ts").read_text(encoding="utf-8") == logger_before
    assert (repo / "lib/logger.ts.proposed").is_file()
    assert [p["path"] for p in data["proposed"]] == ["lib/logger.ts"]
    env_after = (repo / ".env.example").read_text(encoding="utf-8")
    assert env_after.startswith(env_before) and "HEALTH_CHECK_TOKEN=" in env_after
    assert "NEXT_PUBLIC_SUPABASE_URL" not in data["env_added"]          # already present, not duplicated


def test_console_calls_listed_with_line_numbers(tmp_path):
    repo = seeded(tmp_path)
    _, data, md = install(tmp_path, repo)
    assert data["console_calls"] == [
        {"path": "app/api/orders/route.ts", "line": 3, "call": "console.log"},
        {"path": "app/api/orders/route.ts", "line": 7, "call": "console.error"},
    ]
    assert "## Console calls to replace with lib/logger" in md
    assert "`app/api/orders/route.ts:7` — `console.error`" in md


def test_console_scan_skips_vendor_and_build_dirs(tmp_path):
    repo = tmp_path / "repo"
    for rel in ("node_modules/pkg/index.js", ".next/server/page.js", "components/ok.tsx"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("console.log('x')\n" if "ok" not in rel else "export const A = 1;\n", encoding="utf-8")
    _, data, md = install(tmp_path, repo)
    assert data["console_calls"] == []
    assert "- none found" in md


def test_dry_run_still_inventories_console_calls(tmp_path):
    repo = seeded(tmp_path)
    res, data, _ = install(tmp_path, repo, "--dry-run")
    assert res.returncode == 0
    assert not (repo / "lib/logger.ts.proposed").exists()
    assert len(data["console_calls"]) == 2
