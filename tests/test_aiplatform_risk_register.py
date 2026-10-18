"""Tests for ai-platform/ai-governance-risk/scripts/risk_register.py."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-governance-risk/scripts/risk_register.py"
FX = REPO_ROOT / "skills/ai-platform/ai-governance-risk/evals/fixtures"
TBD = "[TO BE BASELINED — owner: AI risk lead]"


def rows(path):
    with path.open(encoding="utf-8") as f:
        return {r["category"]: r for r in csv.DictReader(f)}


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_register_from_medium_canvas(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-case-canvas.md"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    rs = rows(tmp_path / "risk-register.csv")
    assert len(rs) == 9
    assert rs["privacy"]["likelihood"] == "3" and rs["privacy"]["impact"] == "3" and rs["privacy"]["rating"] == "Medium"
    assert rs["privacy"]["owner"] == "HR Ops Lead" and rs["privacy"]["control_id"].startswith("C01; C02; C03; C04")
    assert rs["hallucination"]["rating"] == "Medium" and rs["transparency"]["rating"] == "Medium"
    assert rs["bias"]["likelihood"] == TBD and rs["bias"]["rating"] == "TBD" and "C08" in rs["bias"]["control_id"]
    assert all(x["control"] for x in rs.values())
    card = (tmp_path / "model-card.md").read_text(encoding="utf-8")
    assert "# Model Card — Benefits enquiry assistant — v0.1" in card
    assert "| Risk tier (internal / EU AI Act summary) | medium / [TO BE BASELINED — owner: AI risk lead] |" in card
    assert "| Retrieval sources | HR policy library (SharePoint) |" in card
    assert "| C02 — Data classification and minimization" in card           # tier minimum control set
    assert "| C08 —" not in card                                             # high-tier-only control not required
    assert "legal review required" in card
    assert "[TO BE BASELINED — owner: AI risk lead]" in card and "[TO BE BASELINED]" not in card.replace(TBD, "")


def test_high_risk_without_control_exits_1(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-case-canvas-high.md"), "--out-dir", str(tmp_path),
                   "--controls", str(FX / "controls-catalog-no-security.md"))
    assert r.returncode == 1 and "without a mapped control: ['security']" in r.stderr
    rs = rows(tmp_path / "risk-register.csv")
    assert rs["security"]["rating"] == "High" and rs["security"]["control_id"] == ""
    assert rs["bias"]["rating"] == "High" and rs["bias"]["control_id"]
    ok = run_script(SCRIPT, str(FX / "use-case-canvas-high.md"), "--out-dir", str(tmp_path / "ok"))
    assert ok.returncode == 0


def test_thin_canvas_invents_nothing(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-case-canvas-thin.md"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    rs = rows(tmp_path / "risk-register.csv")
    assert all(x["rating"] == "TBD" and x["likelihood"] == TBD and x["impact"] == TBD for x in rs.values())
    assert all(x["control_id"] for x in rs.values())
    card = (tmp_path / "model-card.md").read_text(encoding="utf-8")
    assert "(tier not stated in canvas)" in card


def test_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, str(tmp_path / "no.md"), "--out-dir", str(tmp_path)).returncode == 1
    nobox = tmp_path / "nobox.md"
    nobox.write_text("# Canvas\nno table here\n", encoding="utf-8")
    assert run_script(SCRIPT, str(nobox), "--out-dir", str(tmp_path)).returncode == 1
    nocat = tmp_path / "nocat.md"
    nocat.write_text("# Controls\n", encoding="utf-8")
    assert run_script(SCRIPT, str(FX / "use-case-canvas.md"), "--out-dir", str(tmp_path), "--controls", str(nocat)).returncode == 1
