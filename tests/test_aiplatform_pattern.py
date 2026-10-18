"""Tests for ai-platform/agent-architecture/scripts/pattern.py."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/agent-architecture/scripts/pattern.py"
FX = REPO_ROOT / "skills/ai-platform/agent-architecture/evals/fixtures"
BASE = {"q1_steps_enumerable": "no", "q2_model_chooses_tools": "yes", "q3_single_agent_fits": "no",
        "q4_blocker": "distinct_expertise", "q5_rubric_exists": "yes", "q6_irreversible_actions": "no"}


def run(tmp_path, answers: dict):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(answers), encoding="utf-8")
    out = tmp_path / "pattern.md"
    return run_script(SCRIPT, str(f), "--out", str(out), "--name", "T"), out


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_fixture_single_agent_with_hitl(tmp_path):
    out = tmp_path / "p.md"
    r = run_script(SCRIPT, str(FX / "answers.json"), "--out", str(out))
    assert r.returncode == 0, r.stderr
    md = out.read_text(encoding="utf-8")
    assert md.splitlines()[2].startswith("**Decision:** Single agent because Q3 = yes")
    assert "| Workflow | Q1 = no: branching cannot be enumerated" in md
    assert "| Router + workflow | Q2 = yes" in md
    assert "HITL checkpoint before every irreversible" in md
    assert "ticket triage paths vary by product line" in md          # evidence quoted


def test_tree_branches(tmp_path):
    r, out = run(tmp_path, {**BASE, "q1_steps_enumerable": "yes"})
    assert r.returncode == 0 and "**Decision:** Workflow because" in out.read_text()
    r, out = run(tmp_path, {**BASE, "q2_model_chooses_tools": "no"})
    assert "**Decision:** Router + workflow" in out.read_text()
    r, out = run(tmp_path, BASE)
    md = out.read_text()
    assert "**Decision:** Supervisor + specialists" in md and "| Single agent | Q3 = no:" in md
    assert "add a bounded Generator + evaluator loop" in md
    r, out = run(tmp_path, {**BASE, "q4_blocker": "parallel_subtasks"})
    assert "**Decision:** Orchestrator + workers" in out.read_text() and "| Fan-out cap | [TO BE BASELINED" in out.read_text()


def test_missing_or_invalid_answers_exit_1(tmp_path):
    r = run_script(SCRIPT, str(FX / "answers-incomplete.json"), "--out", str(tmp_path / "p.md"))
    assert r.returncode == 1 and "unanswered question(s): ['q4_blocker'" in r.stderr
    r, _ = run(tmp_path, {**BASE, "q4_blocker": "magic"})
    assert r.returncode == 1 and "invalid answer" in r.stderr
    r, _ = run(tmp_path, {**BASE, "q7": "yes"})
    assert r.returncode == 1 and "unknown keys" in r.stderr
    assert run_script(SCRIPT, str(tmp_path / "nope.json"), "--out", str(tmp_path / "p.md")).returncode == 1
