"""Tests for ai-platform/ai-strategy-coe/scripts/maturity.py."""
from __future__ import annotations

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-strategy-coe/scripts/maturity.py"
FX = REPO_ROOT / "skills/ai-platform/ai-strategy-coe/evals/fixtures"


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_overall_is_minimum_and_one_item_per_gap(tmp_path):
    r = run_script(SCRIPT, str(FX / "maturity-scorecard.csv"), "--out-dir", str(tmp_path), "--org", "Northwind")
    assert r.returncode == 0, r.stderr
    md = (tmp_path / "maturity.md").read_text(encoding="utf-8")
    assert "Level 1 (Ad hoc) overall; constraining dimension: governance" in md
    gaps = md.split("## Gaps")[1]
    assert all(f"| {d} |" in gaps for d in ("data", "talent", "governance", "value")) and "| platform |" not in gaps
    assert "Enterprise catalog with owners; documented quality rules" in gaps      # next-level criteria from the model
    road = (tmp_path / "roadmap.md").read_text(encoding="utf-8")
    assert "# AI Roadmap — Northwind" in road
    assert "- Maturity: Level 1 (Ad hoc) overall" in road
    assert "| Platform | 3 (Defined) |" in road
    items = road.split("## Gap closure items")[1].split("## Assumptions")[0]
    assert items.count("\n| ") == 5 and "| 4 | value | 2 (Emerging) | 3 |" in items


def test_unevidenced_scores_are_tbd_with_owner(tmp_path):
    r = run_script(SCRIPT, str(FX / "maturity-scorecard-thin.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    md = (tmp_path / "maturity.md").read_text(encoding="utf-8")
    assert "| data | [TO BE BASELINED — owner: CDO] |" in md and "score given without evidence" in md
    assert "| value | [TO BE BASELINED — owner: AI CoE lead] |" in md
    assert "Level 2 (Emerging) overall; constraining dimension: governance — provisional: 3 dimension(s) unscored" in md


def test_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, str(tmp_path / "nope.csv"), "--out-dir", str(tmp_path)).returncode == 1
    bad = tmp_path / "bad.csv"
    bad.write_text("dimension,score_1_to_5,evidence\ndata,7,x\n", encoding="utf-8")
    r = run_script(SCRIPT, str(bad), "--out-dir", str(tmp_path))
    assert r.returncode == 1 and "must be 1-5" in r.stderr
    assert run_script(SCRIPT, str(FX / "maturity-scorecard.csv"), "--out-dir", str(tmp_path), "--target", "9").returncode == 1
