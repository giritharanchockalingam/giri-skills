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


# --- brownfield: extend an existing golden set (--existing) ---

def _merge(tmp_path, new_csv: Path, existing: Path = FX / "golden-set-v1.csv"):
    out, rec, rep = tmp_path / "golden.csv", tmp_path / "rec.csv", tmp_path / "merge.json"
    r = run_script(SCRIPT, str(new_csv), "--existing", str(existing), "--out", str(out),
                   "--outputs-out", str(rec), "--merge-report", str(rep))
    return r, out, rec, rep


def test_merge_keeps_ids_skips_duplicates_and_continues_numbering(tmp_path):
    import json
    r, out, rec, rep = _merge(tmp_path, FX / "cases-new.csv")
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [x["id"] for x in rows] == [f"GS-{i:04d}" for i in range(1, 8)]
    assert rows[0]["notes"].startswith("fictional fixture: golden set v1")  # existing rows kept verbatim
    m = json.loads(rep.read_text())
    assert (m["existing"], m["added"], m["duplicates_skipped"], m["total"]) == (5, 2, 1, 7)
    assert m["skipped"][0]["existing_id"] == "GS-0001"
    outs = {x["id"]: x["output"] for x in csv.DictReader(rec.open(encoding="utf-8"))}
    assert set(outs) == {f"GS-{i:04d}" for i in range(1, 8)}  # existing outputs column + new outputs


def test_merge_existing_expected_is_never_used_as_output(tmp_path):
    existing = tmp_path / "golden.csv"
    existing.write_text("id,category,input,expected,must_contain\nGS-0001,x,Q one,The ideal answer,ideal\n",
                        encoding="utf-8")
    new = tmp_path / "new.csv"
    new.write_text("input,must_contain,output\nQ two,two,answer two\n", encoding="utf-8")
    r, out, rec, _ = _merge(tmp_path, new, existing)
    assert r.returncode == 0, r.stderr
    outs = {x["id"]: x["output"] for x in csv.DictReader(rec.open(encoding="utf-8"))}
    assert outs == {"GS-0002": "answer two"}


def test_merge_id_collision_and_missing_ids_rejected(tmp_path):
    new = tmp_path / "new.csv"
    new.write_text("id,input\nGS-0003,A brand new question\n", encoding="utf-8")
    r, *_ = _merge(tmp_path, new)
    assert r.returncode != 0 and "already exists" in r.stderr
    bad = tmp_path / "bad.csv"
    bad.write_text("id,input\n,Q without id\n", encoding="utf-8")
    r, *_ = _merge(tmp_path, FX / "cases-new.csv", bad)
    assert r.returncode != 0 and "without an id" in r.stderr


def test_merged_set_scores_against_baseline(tmp_path):
    import json
    r, out, rec, _ = _merge(tmp_path, FX / "cases-new.csv")
    sc = tmp_path / "sc.json"
    r = run_script(RUN_EVALS, "--golden", str(out), "--rubric", str(RUBRIC), "--outputs", str(rec), "--out", str(sc),
                   "--threshold", "0.9", "--skip-judge", "--baseline", str(FX / "scorecard-baseline.json"),
                   "--max-regression", "0.02")
    assert r.returncode == 0, r.stdout + r.stderr
    vb = json.loads(sc.read_text())["vs_baseline"]
    assert vb == {"baseline_pass_rate": 0.8333, "delta": 0.1667, "newly_failing": [], "newly_passing": ["GS-0005"],
                  "new_cases": ["GS-0006", "GS-0007"], "dropped_cases": []}
