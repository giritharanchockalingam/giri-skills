"""Harness layer 6: the pipeline's own regression set (docs/HARNESS.md). Fixtures are the real run.json of greenfield
G1 from Oct 26 2026: batch 1 (stopped at architecture: 'invented layout') and batch 2 (6 of 7 stages, 73 tests, one
visual-check repair turn)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pipeline_eval_t", REPO / "scripts" / "pipeline_eval.py")
pe = importlib.util.module_from_spec(spec)
sys.modules["pipeline_eval_t"] = pe
spec.loader.exec_module(pe)
FIX = REPO / "tests" / "fixtures" / "pipeline_eval"
S = {"title": "G1", "expect": {"exit": 0, "min_stages_passed": 6, "visual": "pass"}}


def test_a_real_passing_run_scores_pass_with_what_its_checks_caught():
    r = pe.score_one("G1", S, FIX / "pass" / "G1")
    assert r["result"] == "PASS" and r["stages_passed"] == "6/7" and r["tests"] == "73 passed"
    assert r["repairs"] == 1 and r["defects_caught"]["visual"] == 1          # the unstyled home page, fixed on a repair turn


def test_a_real_failing_run_scores_fail_and_names_where_it_stopped():
    r = pe.score_one("G1", S, FIX / "fail" / "G1")
    assert r["result"] == "FAIL" and r["stopped_at"] == "architecture" and "plan-refine" in r["stop_detail"]


def test_an_expected_acceptance_review_that_never_ran_is_a_fail_not_a_pass():
    r = pe.score_one("G1", {**S, "expect": {**S["expect"], "acceptance": "pass"}}, FIX / "pass" / "G1")
    assert r["result"] == "FAIL" and r["checks"]["acceptance"] is False      # batch 2 predates the acceptance gate


def test_a_scenario_without_a_run_is_not_run(tmp_path):
    assert pe.score_one("G9", S, tmp_path / "G9")["result"] == "NOT RUN"


def test_compare_flags_a_scenario_that_passed_in_the_baseline_and_fails_now(tmp_path):
    base = pe.scorecard(tmp_path, [pe.score_one("G1", S, FIX / "pass" / "G1")])
    now = pe.scorecard(tmp_path, [pe.score_one("G1", S, FIX / "fail" / "G1")])
    regs = pe.compare(now, base, 0.3)
    assert any(r.startswith("G1: passed in the baseline, FAIL now (architecture") for r in regs)
    assert any("pass rate 0%" in r for r in regs)
    assert pe.compare(base, base, 0.3) == []


def test_compare_flags_a_cost_rise_beyond_tolerance(tmp_path):
    base = {"scenarios": [], "pass_rate": 1.0, "median_cost_usd": 2.0}
    assert pe.compare({"scenarios": [], "pass_rate": 1.0, "median_cost_usd": 2.5}, base, 0.3) == []
    assert pe.compare({"scenarios": [], "pass_rate": 1.0, "median_cost_usd": 2.7}, base, 0.3) == ["median cost $2.70 > baseline $2.00 + 30%"]


def test_the_committed_scenarios_are_complete():
    sc = pe.scenarios(None, "core")
    assert [sid for sid, _, _ in sc] == ["G1", "G2", "G3"]
    for sid, s, d in sc:
        brief = json.loads((d / "brief.json").read_text())
        assert s["request"] and s["expect"]["acceptance"] == "pass" and brief["goals"], sid
