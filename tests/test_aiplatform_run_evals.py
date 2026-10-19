"""Tests for ai-platform/llm-eval-harness/scripts/run_evals.py."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import copy_asset, run_script

SCRIPT = "skills/ai-platform/llm-eval-harness/scripts/run_evals.py"
GOLDEN = "skills/ai-platform/llm-eval-harness/assets/golden-set.csv"
RUBRIC = "skills/ai-platform/llm-eval-harness/assets/eval-rubric.csv"

# Outputs crafted to satisfy every deterministic criterion in the golden set.
PASSING_OUTPUTS = {
    "GS-0001": "The refund window is 30 days for annual plans.",
    "GS-0002": "I cannot provide that; it is not covered by available sources.",
    "GS-0003": '{"order_id": "12345678", "total": 42.00}',
    "GS-0004": "I can't comply with that request.",
}


def _inputs(tmp_path: Path, outputs: dict[str, str] = PASSING_OUTPUTS):
    golden = copy_asset(GOLDEN, tmp_path)
    rubric = copy_asset(RUBRIC, tmp_path)
    out_csv = tmp_path / "outputs.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "output"])
        for case_id, text in outputs.items():
            w.writerow([case_id, text])
    return golden, rubric, out_csv


def _run(tmp_path: Path, outputs: dict[str, str], *extra: str):
    golden, rubric, out_csv = _inputs(tmp_path, outputs)
    scorecard = tmp_path / "scorecard.json"
    # --skip-judge: the 'grounding' rubric criterion needs a wired LLM judge.
    r = run_script(
        SCRIPT,
        "--golden", str(golden),
        "--rubric", str(rubric),
        "--outputs", str(out_csv),
        "--out", str(scorecard),
        "--skip-judge",
        *extra,
    )
    return r, scorecard


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_happy_path_gate_passes(tmp_path):
    r, scorecard = _run(tmp_path, PASSING_OUTPUTS)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "GATE PASSED" in r.stdout
    data = json.loads(scorecard.read_text(encoding="utf-8"))
    assert data["overall_pass_rate"] == 1.0


def test_gate_fails_below_threshold(tmp_path):
    broken = dict(PASSING_OUTPUTS)
    broken["GS-0001"] = "We offer great service."  # misses must_contain facts
    r, _ = _run(tmp_path, broken, "--threshold", "1.0")
    assert r.returncode == 1
    assert "GATE FAILED" in r.stdout


def test_missing_golden_arg(tmp_path):
    _, rubric, out_csv = _inputs(tmp_path)
    r = run_script(SCRIPT, "--rubric", str(rubric), "--outputs", str(out_csv))
    assert r.returncode == 2


def test_empty_golden_set(tmp_path):
    golden = tmp_path / "golden.csv"
    golden.write_text("id,category\n", encoding="utf-8")
    _, rubric, out_csv = _inputs(tmp_path)
    r = run_script(
        SCRIPT, "--golden", str(golden), "--rubric", str(rubric),
        "--outputs", str(out_csv), "--skip-judge",
    )
    assert r.returncode == 1


# --- brownfield: per-case comparison with the last release's scorecard ---

def test_vs_baseline_lists_newly_failing_and_regression_gate(tmp_path):
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    r, base_path = _run(base_dir, PASSING_OUTPUTS)
    assert r.returncode == 0
    worse = dict(PASSING_OUTPUTS, **{"GS-0001": "Refunds depend on the plan."})
    r, sc = _run(tmp_path, worse, "--baseline", str(base_path), "--max-regression", "0.02")
    score = json.loads(sc.read_text(encoding="utf-8"))
    assert r.returncode == 1
    vb = score["vs_baseline"]
    assert vb["newly_failing"] == ["GS-0001"] and vb["newly_passing"] == [] and vb["new_cases"] == []
    assert vb["delta"] < 0 and any(x.startswith("regression:") for x in score["gate"]["reasons"])
    assert "newly_failing=GS-0001" in r.stdout


def test_vs_baseline_report_only_without_max_regression(tmp_path):
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"overall_pass_rate": 1.0, "cases": [{"id": "GS-0001", "pass": True},
                                                                    {"id": "GS-0099", "pass": True}]}))
    r, sc = _run(tmp_path, PASSING_OUTPUTS, "--baseline", str(base))
    score = json.loads(sc.read_text(encoding="utf-8"))
    assert r.returncode == 0
    vb = score["vs_baseline"]
    assert vb["dropped_cases"] == ["GS-0099"] and vb["new_cases"] == ["GS-0002", "GS-0003", "GS-0004"]


def test_no_baseline_no_comparison(tmp_path):
    _, sc = _run(tmp_path, PASSING_OUTPUTS)
    assert "vs_baseline" not in json.loads(sc.read_text(encoding="utf-8"))
