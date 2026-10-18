"""Tests for build/observability-setup/scripts/install.py."""
from __future__ import annotations

import json
import shutil

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/observability-setup/scripts/install.py"
SK = REPO_ROOT / "skills/build/observability-setup"
FX = SK / "evals/fixtures"
EXPECTED = ["lib/logger.ts", "lib/logger/context.ts", "app/api/health/route.ts", "app/api/health/deep/route.ts",
            "ops/alerts.yaml", "docs/observability.md"]


def run(tmp_path, target, *extra):
    j, m = tmp_path / "install-report.json", tmp_path / "install-report.md"
    res = run_script(SCRIPT, "--target", str(target), *extra, "--report-json", str(j), "--report-md", str(m))
    data = json.loads(j.read_text(encoding="utf-8")) if j.exists() else None
    return res, data, m


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_fresh_install_writes_everything(tmp_path):
    repo = tmp_path / "repo"
    res, data, md = run(tmp_path, repo, "--project", "demo-app")
    assert res.returncode == 0, res.stderr
    for rel in EXPECTED:
        assert (repo / rel).is_file(), rel
        assert rel in data["written"]
    assert ".env.example" in data["written"]
    env = (repo / ".env.example").read_text(encoding="utf-8")
    assert "HEALTH_CHECK_TOKEN=" in env and "LOG_LEVEL=" in env and "VERCEL_ENV" not in env
    assert data["env_added"] == ["HEALTH_CHECK_TOKEN", "LOG_LEVEL", "LOG_PRETTY", "NEXT_PUBLIC_SUPABASE_URL", "SERVICE_NAME"]
    assert (repo / "docs/observability.md").read_text(encoding="utf-8").startswith("# Observability — demo-app")
    assert (repo / "lib/logger.ts").read_text(encoding="utf-8") == (SK / "assets/logger.ts").read_text(encoding="utf-8")
    text = md.read_text(encoding="utf-8")
    assert "## Written" in text and "## Proposed" in text and "## Next steps" in text


def test_second_run_is_idempotent(tmp_path):
    repo = tmp_path / "repo"
    run(tmp_path, repo)
    res, data, _ = run(tmp_path, repo)
    assert res.returncode == 0
    assert data["written"] == [] and data["proposed"] == [] and data["env_added"] == []
    assert sorted(s["path"] for s in data["skipped"]) == sorted(EXPECTED)


def test_existing_file_is_proposed_not_overwritten(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FX / "repo-existing", repo)
    before = (repo / "lib/logger.ts").read_text(encoding="utf-8")
    res, data, _ = run(tmp_path, repo)
    assert res.returncode == 0, res.stderr
    assert (repo / "lib/logger.ts").read_text(encoding="utf-8") == before
    assert (repo / "lib/logger.ts.proposed").is_file()
    assert data["proposed"][0]["path"] == "lib/logger.ts"
    env = (repo / ".env.example").read_text(encoding="utf-8")
    assert env.startswith("NEXT_PUBLIC_SUPABASE_URL=\n") and "HEALTH_CHECK_TOKEN=" in env
    assert "NEXT_PUBLIC_SUPABASE_URL" not in data["env_added"]   # already present


def test_dry_run_writes_nothing(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FX / "repo-existing", repo)
    files_before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file())
    res, data, md = run(tmp_path, repo, "--dry-run")
    assert res.returncode == 0
    assert data["dry_run"] is True and data["proposed"][0]["path"] == "lib/logger.ts"
    assert sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file()) == files_before
    assert "Dry run" in md.read_text(encoding="utf-8")


def test_bad_input_exits_1(tmp_path):
    f = tmp_path / "file"
    f.write_text("x", encoding="utf-8")
    assert run_script(SCRIPT, "--target", str(f)).returncode == 1
