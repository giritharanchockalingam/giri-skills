"""Tests for presales/sow-drafter/scripts/sow_from_proposal.py."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/sow-drafter/scripts/sow_from_proposal.py"
SK = REPO_ROOT / "skills/presales/sow-drafter"
FX = SK / "evals/fixtures"
TMPL = SK / "assets/sow-template.md"


def run(tmp_path, proposal):
    sow, dl, ac = tmp_path / "SOW.md", tmp_path / "d.csv", tmp_path / "a.csv"
    r = run_script(SCRIPT, str(proposal), "--template", str(TMPL), "--out", str(sow), "--deliverables", str(dl),
                   "--assumptions-check", str(ac))
    return r, sow, dl, ac


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_sow_from_fixture(tmp_path):
    r, sow, dl, ac = run(tmp_path, FX / "proposal.md")
    assert r.returncode == 0, r.stderr
    text = sow.read_text(encoding="utf-8")
    assert text.startswith("# Statement of Work — Northwind Retail — Order Hub Integration")
    assert "| S-01 | Deliver Interface inventory and complexity scores (Wave 0) |" in text
    assert "| O-02 | store POS replacement | S-02 |" in text
    assert "| D-03 | Cutover runbook | Step list with rollback | Markdown | [TO BE BASELINED — owner: ___] |" in text
    assert "| A-02 | No cutover inside the peak freeze" in text
    assert "| D-02 | A | R | R | I | C | C |" in text                 # RACI stub
    assert "## 10. Change control" in text and "CR-nn" in text          # clause from template
    assert "| M2 | Wave 1 cutover | week 16 | D-02, D-03 | test data |" in text
    assert "<" not in text
    rows = list(csv.DictReader(dl.open(encoding="utf-8")))
    assert [r_["id"] for r_ in rows] == ["D-01", "D-02", "D-03"]
    assert all(r_["acceptance"] for r_ in rows)
    assert rows[2]["acceptance"].startswith("[TO BE BASELINED")
    assert ac.read_text(encoding="utf-8").strip() == "id,assumption,status"   # every assumption carried


def test_thin_proposal_marks_acceptance_tbd(tmp_path):
    r, sow, dl, ac = run(tmp_path, FX / "proposal-thin.md")
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader(dl.open(encoding="utf-8")))
    assert all(r_["acceptance"] == "[TO BE BASELINED — owner: ___]" for r_ in rows)
    assert "proposal carries no assumption register" in sow.read_text(encoding="utf-8")


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.md")[0].returncode == 1
    bad = tmp_path / "bad.md"
    bad.write_text("# Acme — X — Proposal\n\n## 1. Executive summary\nhello\n", encoding="utf-8")
    r = run(tmp_path, bad)[0]
    assert r.returncode == 1 and "Scope and deliverables" in r.stderr
