"""Tests for build/ci-cd-vercel-github/scripts/install_ci.py."""
from __future__ import annotations

import json
import shutil

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/ci-cd-vercel-github/scripts/install_ci.py"
SK = REPO_ROOT / "skills/build/ci-cd-vercel-github"
FX = SK / "evals/fixtures"


def run(tmp_path, target):
    j, m = tmp_path / "ci-report.json", tmp_path / "ci-report.md"
    res = run_script(SCRIPT, "--target", str(target), "--report-json", str(j), "--report-md", str(m))
    data = json.loads(j.read_text(encoding="utf-8")) if j.exists() else None
    return res, data, m


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_fresh_install_writes_and_validates(tmp_path):
    repo = tmp_path / "repo"
    res, data, md = run(tmp_path, repo)
    assert res.returncode == 0, res.stderr
    assert data["ok"] is True
    for name in ("ci.yml", "preview.yml", "prod.yml"):
        assert (repo / ".github/workflows" / name).read_text(encoding="utf-8") == \
            (SK / "assets/workflows" / name).read_text(encoding="utf-8")
    by = {w["workflow"]: w for w in data["workflows"]}
    assert all(w["action"] == "written" and w["valid"] and not w["missing_jobs"] for w in by.values())
    assert by["ci.yml"]["jobs_found"] == ["lint-typecheck-test", "rls-lint", "secrets-scan"]
    assert by["prod.yml"]["jobs_found"] == ["verify-tag", "migrate-staging", "migrate-prod", "deploy-prod"]
    text = md.read_text(encoding="utf-8")
    assert "gate: PASS" in text and "## Workflows" in text and "## Branch protection" in text


def test_existing_workflow_kept_and_missing_jobs_fail(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FX / "repo-custom-ci", repo)
    before = (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    res, data, md = run(tmp_path, repo)
    assert res.returncode == 1
    assert (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8") == before   # never overwritten
    ci = next(w for w in data["workflows"] if w["workflow"] == "ci.yml")
    assert ci["action"] == "kept" and ci["missing_jobs"] == ["rls-lint", "secrets-scan"]
    assert data["ok"] is False and "gate: FAIL" in md.read_text(encoding="utf-8")
    assert "rls-lint" in res.stderr


def test_malformed_workflow_is_invalid(tmp_path):
    repo = tmp_path / "repo"
    wf = repo / ".github/workflows"
    wf.mkdir(parents=True)
    (wf / "preview.yml").write_text("name: preview\nsteps:\n  - run: echo hi\n", encoding="utf-8")
    res, data, _ = run(tmp_path, repo)
    assert res.returncode == 1
    pv = next(w for w in data["workflows"] if w["workflow"] == "preview.yml")
    assert pv["valid"] is False and "missing top-level on:" in pv["problems"] and "missing top-level jobs:" in pv["problems"]


def test_bad_input_exits_1(tmp_path):
    f = tmp_path / "file"
    f.write_text("x", encoding="utf-8")
    assert run_script(SCRIPT, "--target", str(f)).returncode == 1
