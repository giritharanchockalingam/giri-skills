"""Tests for career/interview-prep/scripts/prep.py."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/career/interview-prep/scripts/prep.py"
SK = REPO_ROOT / "skills/career/interview-prep"
FX = SK / "evals/fixtures"


def run(tmp_path: Path, stories: Path, round_: str = "panel", jd: Path = FX / "jd.txt"):
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--jd", str(jd), "--stories", str(stories), "--round", round_, "--out-dir", str(out), cwd=SK)
    return r, out


def comp_rows(out: Path) -> dict[str, dict]:
    return {r["competency"]: r for r in csv.DictReader((out / "competency-map.csv").open(encoding="utf-8"))}


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_maps_every_competency_to_stories_or_gap(tmp_path):
    r, out = run(tmp_path, FX / "story-bank.md")
    assert r.returncode == 0, r.stderr
    m = comp_rows(out)
    assert len(m) == 10 and {x["status"] for x in m.values()} <= {"mapped", "GAP"}
    assert m["C4"]["story_ids"] == "SB-01;SB-03;SB-07" and m["C4"]["in_jd"] == "yes"
    assert m["C7"]["story_ids"] == "SB-06" and "SOX" in m["C7"]["jd_evidence"]
    assert list(m)[0] == "C7"                                   # ranked by JD emphasis
    pack = (out / "prep-pack.md").read_text(encoding="utf-8")
    assert "**[SB-01] Claims platform modernization**" in pack
    assert "- R: Auto-adjudication 71% → 88%" in pack            # quoted from the bank, not rewritten
    assert "## Likely questions — panel (Round 3)" in pack and "| How technical are you? |" in pack
    ask = (out / "questions-to-ask.md").read_text(encoding="utf-8")
    assert "## Panel — peers" in ask and "## Recruiter" not in ask


def test_competency_without_story_is_gap_not_invented(tmp_path):
    r, out = run(tmp_path, FX / "story-bank-thin.md", "executive")
    assert r.returncode == 0, r.stderr
    m = comp_rows(out)
    assert m["C7"]["status"] == "GAP" and m["C7"]["story_ids"] == ""
    assert m["C4"]["status"] == "mapped"
    pack = (out / "prep-pack.md").read_text(encoding="utf-8")
    assert "GAP — no story in the bank for C7" in pack
    assert "SB-06" not in pack                                   # that story is not in the thin bank
    assert "## CIO / CTO" in (out / "questions-to-ask.md").read_text(encoding="utf-8")


def test_hiring_manager_questions_pair_with_story_ids(tmp_path):
    r, out = run(tmp_path, FX / "story-bank.md", "hiring-manager")
    assert r.returncode == 0, r.stderr
    pack = (out / "prep-pack.md").read_text(encoding="utf-8")
    assert "| Tell me about a transformation you led end to end. | C4 | STAR+R with before/after KPI | SB-01, SB-03, SB-07 |" in pack


def test_90_day_plan_uses_jd_and_owned_markers(tmp_path):
    r, out = run(tmp_path, FX / "story-bank.md", "executive")
    assert r.returncode == 0, r.stderr
    plan = (out / "90-day-plan.md").read_text(encoding="utf-8")
    assert plan.startswith("# 90-Day Plan — Vice President, Enterprise Applications")
    assert "owns claims, enrollment and ERP platforms" in plan    # JD sentence
    assert "owner: ___" not in plan and "[TO BE BASELINED — owner: Hiring manager]" in plan
    assert "## Focus areas from the JD" in plan and "### C7 Risk, security and compliance" in plan


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.md")[0].returncode == 1
    no_ids = tmp_path / "stories.md"
    no_ids.write_text("# stories\n\nsome prose\n", encoding="utf-8")
    r = run(tmp_path, no_ids)[0]
    assert r.returncode == 1 and "SB-nn" in r.stderr
    assert run(tmp_path, FX / "story-bank.md", "board")[0].returncode == 2   # argparse choices
