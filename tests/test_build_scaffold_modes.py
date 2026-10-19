"""Brownfield ("existing") path of build/project-bootstrap: kept files are compared with the standard."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/project-bootstrap"
SCAFFOLD = SK / "scripts/scaffold.py"
SEED = SK / "scripts/seed_repo.py"
FX = SK / "evals/fixtures/repo-existing"


def test_existing_files_kept_and_section_gaps_reported(tmp_path):
    proj = tmp_path / "proj"
    assert run_script(SEED, "--from", str(FX), "--target", str(proj)).returncode == 0
    spec_before = (proj / "docs/SPEC.md").read_text(encoding="utf-8")
    rep = tmp_path / "report.json"
    r = run_script(SCAFFOLD, "--target", str(proj), "--name", "tidewater-booking", "--report", str(rep))
    assert r.returncode == 0, r.stderr
    assert (proj / "docs/SPEC.md").read_text(encoding="utf-8") == spec_before
    data = json.loads(rep.read_text(encoding="utf-8"))
    assert data["kept"] == ["docs/SPEC.md", "CLAUDE.md"]
    assert ".github/workflows/ci.yml" in data["written"]
    gaps = {g["path"]: g["missing"] for g in data["gaps"]}
    # '## Users' covers 'Users and jobs to be done'; '## Scope' and '## Purpose' are present
    assert gaps["docs/SPEC.md"] == ["Non-functional requirements", "Architecture", "Data model", "Integrations",
                                    "Risks", "Open questions", "Milestones"]
    assert gaps["CLAUDE.md"] == ["Stack conventions", "Gates", "Where things live", "Do not"]
    assert "gap    docs/SPEC.md: missing sections — Non-functional requirements" in r.stdout


def test_fresh_scaffold_report_has_no_gaps(tmp_path):
    rep = tmp_path / "report.json"
    r = run_script(SCAFFOLD, "--target", str(tmp_path / "p"), "--name", "demo", "--report", str(rep))
    assert r.returncode == 0
    data = json.loads(rep.read_text(encoding="utf-8"))
    assert data["kept"] == [] and data["gaps"] == [] and "docs/SPEC.md" in data["written"]


def test_rerun_on_own_scaffold_reports_no_gaps(tmp_path):
    proj = tmp_path / "p"
    run_script(SCAFFOLD, "--target", str(proj), "--name", "demo")
    rep = tmp_path / "report.json"
    r = run_script(SCAFFOLD, "--target", str(proj), "--name", "demo", "--report", str(rep))
    data = json.loads(rep.read_text(encoding="utf-8"))
    assert r.returncode == 0 and data["written"] == [] and data["gaps"] == []


def test_dry_run_reports_gaps_without_writing(tmp_path):
    proj = tmp_path / "proj"
    run_script(SEED, "--from", str(FX), "--target", str(proj))
    r = run_script(SCAFFOLD, "--target", str(proj), "--name", "x", "--dry-run")
    assert r.returncode == 0 and "gap    CLAUDE.md" in r.stdout
    assert not (proj / "docs/HANDOFF.md").exists()
