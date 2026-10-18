"""Tests for presales/competitive-positioning/scripts/battle_card.py."""
from __future__ import annotations

from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/competitive-positioning/scripts/battle_card.py"
FX = REPO_ROOT / "skills/presales/competitive-positioning/evals/fixtures"


def run(tmp_path, ours, theirs, concerns=None):
    out = tmp_path / "bc.md"
    r = run_script(SCRIPT, str(ours), str(theirs), str(concerns or FX / "concerns.csv"), "--out", str(out),
                   "--client", "Northwind", "--alternative", "Incumbent SI")
    return r, out


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_wedge_landmines_objections(tmp_path):
    r, out = run(tmp_path, FX / "our-capabilities.csv", FX / "their-claims.csv")
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "**INTERNAL — do not distribute.**" in text
    wedge = text.split("## Wedge")[1].split("## Landmines")[0]
    assert "Peak-season cutover rehearsal and parallel run | Peak-season cutover experience (them: 2) | CTO:" in wedge
    assert "Fixed-price waves with explicit P80 contingency | Fixed-price commitment on migration (them: 1) | CFO:" in wedge
    assert "Apigee X platform engineering" not in wedge                 # strong, but no weak claim / concern
    assert '| Attack their claim "Lower blended rate" | rated 4/5' in text
    obj = text.split("## Objection handling")[1].split("## Ghost lines")[0]
    cfo = next(ln for ln in obj.splitlines() if ln.startswith("| Fixed price and no surprises"))
    cells = [c.strip() for c in cfo.strip("|").split("|")]
    assert len(cells) == 5 and cells[2] == "Position on: Fixed-price waves with explicit P80 contingency"
    assert cells[4].startswith("What would you need to see")
    vp = next(ln for ln in obj.splitlines() if ln.startswith("| Knowledge of the current MuleSoft estate"))
    assert vp.count("[TO BE BASELINED — owner: Bid manager]") == 2             # reframe + proof unknown


def test_thin_inputs_no_wedge_and_hypotheses(tmp_path):
    r, out = run(tmp_path, FX / "our-capabilities-thin.csv", FX / "their-claims-thin.csv")
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "No wedge found" in text and "(hypothesis)" in text
    assert "| none on current evidence |" in text


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.csv", FX / "their-claims.csv")[0].returncode == 1
    bad = tmp_path / "bad.csv"
    bad.write_text("capability,evidence,strength\nX,,9\n", encoding="utf-8")
    r = run(tmp_path, bad, FX / "their-claims.csv")[0]
    assert r.returncode == 1 and "strength must be 1-5" in r.stderr
    nocol = tmp_path / "nc.csv"
    nocol.write_text("stakeholder\nCTO\n", encoding="utf-8")
    assert run(tmp_path, FX / "our-capabilities.csv", FX / "their-claims.csv", nocol)[0].returncode == 1
