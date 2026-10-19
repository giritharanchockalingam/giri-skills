"""career/interview-prep: --previous-round debrief."""
from __future__ import annotations

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/career/interview-prep"
FX = SK / "evals/fixtures"


def prep(tmp_path, *extra):
    r = run_script(SK / "scripts/prep.py", "--jd", str(FX / "jd.txt"), "--stories", str(FX / "story-bank.md"),
                   "--round", "panel", "--competencies", str(SK / "references/competency-map.md"),
                   "--questions", str(SK / "references/question-bank.md"), "--ask", str(SK / "references/questions-to-ask.md"),
                   "--plan-template", str(SK / "assets/90-day-plan.md"), "--out-dir", str(tmp_path), *extra)
    pack = tmp_path / "prep-pack.md"
    return r, (pack.read_text(encoding="utf-8") if pack.exists() else "")


def test_debrief_marks_told_and_spent(tmp_path):
    r, pack = prep(tmp_path, "--previous-round", str(FX / "debrief-round2.md"))
    assert r.returncode == 0, r.stderr
    assert "Stories already told: SB-01, SB-02" in pack
    assert "**[SB-01] Claims platform modernization** (tagged C4, C1, C6) — told in the last round" in pack
    assert "every story already told — bring new depth | SB-02 |" in pack
    assert "- What would your first 90 days look like?" in pack
    assert pack.index("## Since the last round") < pack.index("## Gaps and how to handle them honestly")


def test_unknown_story_id_reported(tmp_path):
    notes = tmp_path / "n.md"
    notes.write_text("Told SB-99 about the merger.\n", encoding="utf-8")
    r, pack = prep(tmp_path, "--previous-round", str(notes))
    assert r.returncode == 0
    assert "Not in the story bank (check the id): SB-99." in pack and "Stories already told: none recorded" in pack


def test_without_debrief_unchanged(tmp_path):
    r, pack = prep(tmp_path)
    assert r.returncode == 0 and "## Since the last round" not in pack and "told in the last round" not in pack
