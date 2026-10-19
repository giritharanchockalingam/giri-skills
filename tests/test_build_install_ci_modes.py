"""Brownfield ("existing") path of build/ci-cd-vercel-github: seed_repo.py and the package.json script check."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/ci-cd-vercel-github"
INSTALL = SK / "scripts/install_ci.py"
SEED = SK / "scripts/seed_repo.py"
FX = SK / "evals/fixtures/repo-existing-ci"


def install(tmp_path, repo):
    j, m = tmp_path / "ci-report.json", tmp_path / "ci-report.md"
    res = run_script(INSTALL, "--target", str(repo), "--report-json", str(j), "--report-md", str(m))
    return res, json.loads(j.read_text(encoding="utf-8")), m.read_text(encoding="utf-8")


def test_seed_copies_dotfiles_and_marks_target(tmp_path):
    repo = tmp_path / "repo"
    res = run_script(SEED, "--from", str(FX), "--target", str(repo))
    assert res.returncode == 0, res.stderr
    assert (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8") == \
        (FX / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert (repo / "package.json").is_file() and (repo / ".seeded-copy").is_file()


def test_seed_reseeds_its_own_copy_but_refuses_a_foreign_repo(tmp_path):
    repo = tmp_path / "repo"
    assert run_script(SEED, "--from", str(FX), "--target", str(repo)).returncode == 0
    (repo / "scratch.txt").write_text("left over", encoding="utf-8")
    assert run_script(SEED, "--from", str(FX), "--target", str(repo)).returncode == 0
    assert not (repo / "scratch.txt").exists()          # a re-run starts clean
    foreign = tmp_path / "real-repo"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("mine", encoding="utf-8")
    res = run_script(SEED, "--from", str(FX), "--target", str(foreign))
    assert res.returncode == 1 and "not seeded by this script" in res.stderr
    assert (foreign / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_seed_rejects_missing_source(tmp_path):
    res = run_script(SEED, "--from", str(tmp_path / "nope"), "--target", str(tmp_path / "repo"))
    assert res.returncode == 1 and "not found" in res.stderr


def test_existing_repo_keeps_ci_and_lists_missing_npm_scripts(tmp_path):
    repo = tmp_path / "repo"
    run_script(SEED, "--from", str(FX), "--target", str(repo))
    before = (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    res, data, md = install(tmp_path, repo)
    assert res.returncode == 0, res.stderr                # every required job present -> gate passes
    assert (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8") == before
    by = {w["workflow"]: w for w in data["workflows"]}
    assert by["ci.yml"]["action"] == "kept" and by["preview.yml"]["action"] == "written"
    assert data["package_json"] == "checked"
    assert by["ci.yml"]["npm_scripts_missing"] == ["build-storybook"]
    assert by["preview.yml"]["npm_scripts_missing"] == ["test:e2e"]
    assert by["prod.yml"]["npm_scripts_missing"] == []
    assert "## package.json scripts" in md and "`npm run test:e2e` — not in package.json scripts" in md


def test_no_package_json_is_reported_not_checked(tmp_path):
    res, data, md = install(tmp_path, tmp_path / "fresh")
    assert res.returncode == 0
    assert data["package_json"] == "absent"
    assert all(w["npm_scripts_missing"] == [] for w in data["workflows"])
    assert "No package.json in the target yet" in md


def test_invalid_package_json_fails(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text("{not json", encoding="utf-8")
    res = run_script(INSTALL, "--target", str(repo), "--report-json", str(tmp_path / "r.json"),
                     "--report-md", str(tmp_path / "r.md"))
    assert res.returncode == 1 and "package.json is not valid JSON" in res.stderr
