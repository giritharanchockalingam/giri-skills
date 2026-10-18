"""Tests for ai-platform/ai-strategy-coe/scripts/score_portfolio.py."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-strategy-coe/scripts/score_portfolio.py"
FX = REPO_ROOT / "skills/ai-platform/ai-strategy-coe/evals/fixtures"


def rows(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_ranking_formula_and_bands(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-cases.csv"), "--out-dir", str(tmp_path), "--org", "Northwind")
    assert r.returncode == 0, r.stderr
    ranked = rows(tmp_path / "portfolio.csv")
    assert [x["id"] for x in ranked][:3] == ["UC-001", "UC-009", "UC-002"]
    by = {x["id"]: x for x in ranked}
    assert by["UC-001"]["score"] == "40.0" and by["UC-001"]["band"] == "Now"       # 4*5*4/2
    assert by["UC-009"]["band"] == "Stop"                                           # V<=2
    assert by["UC-008"]["band"] == "Stop"                                           # R=5
    assert by["UC-004"]["score"] == "8.0" and by["UC-004"]["band"] == "Later"
    assert by["UC-005"]["business_owner"] == "[TO BE BASELINED — owner: AI CoE lead]"
    assert all(x["score"] for x in ranked)
    assert rows(tmp_path / "unscored.csv") == []
    md = (tmp_path / "portfolio.md").read_text(encoding="utf-8")
    assert "## Quadrant summary" in md and "| Quick win (V>=3, F>=3) | 5 |" in md
    assert "Fewer than 8 candidates" not in md


def test_missing_axis_goes_to_unscored_bucket(tmp_path):
    r = run_script(SCRIPT, str(FX / "use-cases-partial.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert [x["id"] for x in rows(tmp_path / "portfolio.csv")] == ["UC-001", "UC-004"]
    un = {x["id"]: x["reason"] for x in rows(tmp_path / "unscored.csv")}
    assert un == {"UC-002": "missing score(s): D", "UC-003": "missing score(s): V, F, D, R"}
    md = (tmp_path / "portfolio.md").read_text(encoding="utf-8")
    assert "Fewer than 8 candidates" in md and "| UC-003 |" in md.split("## Unscored")[1]


def test_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, str(tmp_path / "nope.csv"), "--out-dir", str(tmp_path)).returncode == 1
    bad = tmp_path / "bad.csv"
    bad.write_text("id,use_case,value_V,feasibility_F,data_readiness_D,risk_R\nUC-1,X,9,1,1,1\n", encoding="utf-8")
    r = run_script(SCRIPT, str(bad), "--out-dir", str(tmp_path))
    assert r.returncode == 1 and "must be 1-5" in r.stderr
    nocol = tmp_path / "nocol.csv"
    nocol.write_text("id,use_case,value_V\nUC-1,X,3\n", encoding="utf-8")
    assert run_script(SCRIPT, str(nocol), "--out-dir", str(tmp_path)).returncode == 1
