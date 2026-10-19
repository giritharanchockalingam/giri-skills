"""presales/sow-drafter: --existing-sow reconciliation against the approved proposal."""
from __future__ import annotations

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/sow-drafter"
SCRIPT = SK / "scripts/sow_from_proposal.py"
FX = SK / "evals/fixtures"


def sow(tmp_path, *extra):
    r = run_script(SCRIPT, str(FX / "proposal.md"), "--template", str(SK / "assets/sow-template.md"),
                   "--out", str(tmp_path / "SOW.md"), "--deliverables", str(tmp_path / "d.csv"),
                   "--assumptions-check", str(tmp_path / "a.csv"), "--reconcile", str(tmp_path / "rec.md"), *extra)
    rec = tmp_path / "rec.md"
    return r, (rec.read_text(encoding="utf-8") if rec.exists() else None)


def test_reconciliation_findings(tmp_path):
    r, rec = sow(tmp_path, "--existing-sow", str(FX / "sow-existing.md"))
    assert r.returncode == 0, r.stderr
    assert "**5 issue(s) to resolve before signature.**" in rec
    assert "| D-01 | Interface inventory and complexity scores | yes |" in rec and "| ok |" in rec
    assert "| D-03 | Cutover runbook | no |" in rec
    assert "| A-02 | No cutover inside the peak freeze 2026-11-10 to 2027-01-05 | no — carry it over |" in rec
    assert "| Change control | no — add the section" in rec


def test_generated_sow_reconciles_clean(tmp_path):
    first = tmp_path / "first"
    first.mkdir()
    sow(first)
    r, rec = sow(tmp_path, "--existing-sow", str(first / "SOW.md"))
    assert r.returncode == 0
    # the only finding left is the proposal's own missing acceptance criterion for D-03
    assert "**1 issue(s) to resolve before signature.**" in rec
    assert "| D-03 | Cutover runbook | yes | — | no acceptance criterion" in rec


def test_no_existing_no_reconciliation(tmp_path):
    r, rec = sow(tmp_path)
    assert r.returncode == 0 and rec is None


def test_missing_existing_fails(tmp_path):
    r, _ = sow(tmp_path, "--existing-sow", str(tmp_path / "nope.md"))
    assert r.returncode == 1 and "file not found" in r.stderr
