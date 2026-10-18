"""Tests for ai-platform/ai-use-case-canvas/scripts/canvas.py."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-use-case-canvas/scripts/canvas.py"
FX = REPO_ROOT / "skills/ai-platform/ai-use-case-canvas/evals/fixtures"


def run(tmp_path, answers: dict):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(answers), encoding="utf-8")
    return run_script(SCRIPT, str(f), "--out-dir", str(tmp_path))


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_full_answers_proceed_and_build(tmp_path):
    r = run_script(SCRIPT, str(FX / "answers.json"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    canvas = (tmp_path / "canvas.md").read_text(encoding="utf-8")
    assert "**Verdict:** Proceed to design" in canvas
    assert "**Next 30-day step:** pull 200 historical enquiries and label 50 with HR SME — owner: HR Ops Lead — by: 2026-10-31" in canvas
    assert "| 3 | Current process and baseline | Volume: 900/mo; time/unit: 12 min; error/cost: [TO BE BASELINED — owner: HR Ops Lead] |" in canvas
    assert "| Priority (V×F×D÷R) | 12.0 |" in canvas and "Hand-off: ai-governance-risk" in canvas
    assert len(canvas.splitlines()) <= 60 and "<" not in canvas.replace("<=", "").replace("->", "")
    dec = (tmp_path / "decision.md").read_text(encoding="utf-8")
    assert dec.splitlines()[2].startswith("**Decision:** build — 3 of 5 factors favor build; strongest: data_sensitivity")
    score = json.loads((tmp_path / "score.json").read_text(encoding="utf-8"))
    assert score["priority"] == 12.0 and score["verdict"] == "Proceed to design" and score["factors"]["buy"] == ["differentiation", "time_to_value"]


def test_missing_data_readiness_means_wait(tmp_path):
    r = run_script(SCRIPT, str(FX / "answers-no-data-readiness.json"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    canvas = (tmp_path / "canvas.md").read_text(encoding="utf-8")
    assert "| Data readiness | [TO BE BASELINED — owner: Legal Ops Lead] |" in canvas
    assert "**Verdict:** TBD — unscored axis/axes: data_readiness" in canvas
    assert "**Decision:** wait — data readiness is unscored" in (tmp_path / "decision.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "score.json").read_text())["priority"] is None


def test_verdict_rules(tmp_path):
    base = {"name": "X", "problem_user": "u", "decision": "d", "value": {"baseline_signed_by": "O"},
            "scores": {"value": 3, "feasibility": 3, "data_readiness": 2, "risk": 2},
            "build_buy": {"differentiation": "buy", "product_fit": "buy"}}
    assert run(tmp_path, base).returncode == 0
    assert "Proceed after data readiness" in (tmp_path / "canvas.md").read_text() and "**Decision:** wait" in (tmp_path / "decision.md").read_text()
    run(tmp_path, {**base, "scores": {**base["scores"], "data_readiness": 3}})
    assert "**Verdict:** Proceed to design" in (tmp_path / "canvas.md").read_text() and "**Decision:** buy" in (tmp_path / "decision.md").read_text()
    run(tmp_path, {**base, "scores": {**base["scores"], "risk": 5}})
    assert "**Verdict:** Stop" in (tmp_path / "canvas.md").read_text()
    run(tmp_path, {**base, "scores": {**base["scores"], "data_readiness": 3}, "build_buy": {"differentiation": "buy", "product_fit": "build"}})
    assert "**Decision:** TBD — tie" in (tmp_path / "decision.md").read_text()
    run(tmp_path, {**base, "problem_user": ""})
    assert "**Verdict:** Stop — no identifiable user" in (tmp_path / "canvas.md").read_text()


def test_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, str(tmp_path / "no.json"), "--out-dir", str(tmp_path)).returncode == 1
    assert run(tmp_path, {"name": "X", "scores": {"value": 9}}).returncode == 1
    assert run(tmp_path, {"name": "X", "build_buy": {"vibes": "build"}}).returncode == 1
    assert run(tmp_path, {"name": "X", "build_buy": {"product_fit": "rent"}}).returncode == 1
    assert run(tmp_path, {"idea": "no name"}).returncode == 1
