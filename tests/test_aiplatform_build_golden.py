"""Tests for ai-platform/llm-eval-harness/scripts/build_golden.py."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/llm-eval-harness/scripts/build_golden.py"
RUN_EVALS = "skills/ai-platform/llm-eval-harness/scripts/run_evals.py"
FX = REPO_ROOT / "skills/ai-platform/llm-eval-harness/evals/fixtures"
RUBRIC = REPO_ROOT / "skills/ai-platform/llm-eval-harness/assets/eval-rubric.csv"

GOLDEN_COLS = ["id", "category", "difficulty", "input", "expected", "must_contain", "must_not_contain",
               "expected_json_valid", "weight", "source", "notes"]


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_csv_source_keeps_columns_and_numbers_ids(tmp_path):
    out, outputs = tmp_path / "g.csv", tmp_path / "o.csv"
    r = run_script(SCRIPT, str(FX / "cases.csv"), "--out", str(out), "--outputs-out", str(outputs))
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert list(rows[0].keys()) == GOLDEN_COLS
    assert [row["id"] for row in rows] == [f"GS-{i:04d}" for i in range(1, len(rows) + 1)]
    assert rows[0]["must_contain"] == "30 days||annual"
    # case with no criteria is flagged for an SME, never invented
    flagged = [row for row in rows if "must_contain [TO BE BASELINED" in row["notes"]]
    assert len(flagged) == 1 and flagged[0]["category"] == "shipping"
    outs = list(csv.DictReader(outputs.open(encoding="utf-8")))
    assert outs[0].keys() == {"id", "output"} and len(outs) == len(rows)


def test_transcript_source(tmp_path):
    out = tmp_path / "g.csv"
    r = run_script(SCRIPT, str(FX / "transcript.md"), "--out", str(out), "--category", "support")
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert len(rows) == 2
    assert rows[0]["input"].startswith("What is the refund window")
    assert rows[0]["expected"].startswith("Annual plans")
    assert rows[0]["category"] == "support" and rows[0]["source"] == "log"
    assert all("[TO BE BASELINED" in row["notes"] for row in rows)


def test_harness_runs_on_output(tmp_path):
    out, outputs = tmp_path / "g.csv", tmp_path / "o.csv"
    assert run_script(SCRIPT, str(FX / "cases.csv"), "--out", str(out), "--outputs-out", str(outputs)).returncode == 0
    r = run_script(RUN_EVALS, "--golden", str(out), "--rubric", str(RUBRIC), "--outputs", str(outputs),
                   "--skip-judge", "--out", str(tmp_path / "score.json"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "GATE PASSED" in r.stdout


def test_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, str(tmp_path / "nope.csv"), "--out", str(tmp_path / "g.csv")).returncode == 1
    bad = tmp_path / "bad.csv"; bad.write_text("question\nhi\n", encoding="utf-8")
    r = run_script(SCRIPT, str(bad), "--out", str(tmp_path / "g.csv"))
    assert r.returncode == 1 and "input" in r.stderr
    empty = tmp_path / "t.md"; empty.write_text("no turns here\n", encoding="utf-8")
    assert run_script(SCRIPT, str(empty), "--out", str(tmp_path / "g.csv")).returncode == 1
