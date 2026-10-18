"""Tests for ai-platform/feedback-improvement-loop/scripts/improve.py (fixtures are fictional)."""
from __future__ import annotations

import csv
import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/feedback-improvement-loop/scripts/improve.py"
FX = REPO_ROOT / "skills/ai-platform/feedback-improvement-loop/evals/fixtures"


def _run(tmp_path, feedback=None, failures=None, min_rows="10", *extra):
    out = tmp_path / "out"
    args = ["--feedback", str(feedback or FX / "feedback.csv"), "--min-rows", min_rows, "--out-dir", str(out), *extra]
    if failures:
        args += ["--eval-failures", str(failures)]
    r = run_script(SCRIPT, *args)
    backlog = list(csv.DictReader((out / "backlog.csv").open(encoding="utf-8"))) if (out / "backlog.csv").exists() else []
    cases = json.loads((out / "new-eval-cases.json").read_text(encoding="utf-8"))["cases"] if (out / "new-eval-cases.json").exists() else []
    md = (out / "improvement-report.md").read_text(encoding="utf-8") if (out / "improvement-report.md").exists() else ""
    return r, backlog, cases, md


def _fb(tmp_path, rows):
    p = tmp_path / "fb.csv"
    p.write_text("# fictional fixture\nid,ts,rating,comment,tags,trace_id,feature\n" + "".join(r + "\n" for r in rows), encoding="utf-8")
    return p


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_happy_path_ranking_hand_checked(tmp_path):
    r, backlog, cases, md = _run(tmp_path, failures=FX / "eval-failures.csv")
    assert r.returncode == 0, r.stderr
    top = [(b["bucket"], b["feature"], b["score"], b["eval_failures"], b["fix_type"]) for b in backlog]
    # hallucination/policy-qa: F01 (1★=3) + F02 (down=3) + F03 (2★=2) = 8; E-07, E-19 linked
    # too-slow/claims-summary: F07 (3) + F11 (tag latency, 3) = 6
    # wrong-format, refusal, other tie at 3 -> wrong-format first (1 eval failure), then taxonomy order
    assert top == [
        ("hallucination", "policy-qa", "8", "2", "retrieval"),
        ("too-slow", "claims-summary", "6", "0", "model"),
        ("wrong-format", "claims-summary", "3", "1", "prompt"),
        ("refusal", "claims-summary", "3", "0", "guardrail"),
        ("other", "policy-qa", "3", "0", "UX"),
        ("missing-info", "policy-qa", "2", "0", "data"),
        ("tone", "policy-qa", "1", "0", "prompt"),
    ]
    assert backlog[0]["mean_severity"] == "2.67" and backlog[0]["eval_case_ids"] == "E-07;E-19"
    assert all(b["owner"].startswith("[TO BE BASELINED — owner: ") and "___" not in b["owner"] for b in backlog)
    assert "F04" not in ";".join(b["feedback_ids"] for b in backlog)           # positive row not an issue
    assert len(cases) == 11
    for sec in ("## Top issues", "## Backlog", "## New eval cases", "## Regression gate"):
        assert sec in md
    assert "1 rejected" in md                                                  # F14 rating 'meh'


def test_eval_cases_repo_shape_and_no_invented_inputs(tmp_path):
    _, _, cases, _ = _run(tmp_path)
    by_id = {c["id"]: c for c in cases}
    c1 = by_id["fil-hallucination-policy-qa-F01"]
    assert set(c1) >= {"id", "prompt", "expected"} and isinstance(c1["expected"], list) and c1["expected"]
    assert c1["prompt"] == "Replay the user input recorded in trace t-101 (feature policy-qa)."
    assert c1["provenance"]["basis"] == "keyword:made up"
    # F03 has no trace_id -> prompt is an owned TBD, not a reconstructed question
    assert by_id["fil-hallucination-policy-qa-F03"]["prompt"].startswith("[TO BE BASELINED — owner: Eval lead]")
    assert len({c["id"] for c in cases}) == len(cases)


def test_grouping_tag_beats_keyword_and_word_boundaries(tmp_path):
    fb = _fb(tmp_path, [
        "A,,1,the format was wrong,tone,,f",                 # tag wins over keyword
        "B,,1,Missing the information I asked for,,,f",      # 'format' inside 'information' must not match
        "C,,down,flagged as fine,,,f",                       # no keyword at a word start -> other
    ])
    r, backlog, _, _ = _run(tmp_path, feedback=fb, min_rows="3")
    assert r.returncode == 0
    assert {b["bucket"]: b["feedback_ids"] for b in backlog} == {"tone": "A", "missing-info": "B", "other": "C"}


def test_cases_per_issue_caps_by_severity(tmp_path):
    fb = _fb(tmp_path, [f"X{i},,{1 if i < 2 else 3},too slow,,t{i},f" for i in range(5)])
    _, backlog, cases, _ = _run(tmp_path, fb, None, "5", "--cases-per-issue", "2")
    assert backlog[0]["score"] == "9"                                          # 3 + 3 + 1 + 1 + 1
    assert [c["provenance"]["feedback_id"] for c in cases] == ["X0", "X1"]


def test_eval_failures_only_group(tmp_path):
    fb = _fb(tmp_path, ["A,,5,great,,,f"])
    ef = tmp_path / "ef.csv"
    ef.write_text("case_id,feature,failure_reason\nE1,g,refused a valid request\n")
    r, backlog, cases, _ = _run(tmp_path, fb, ef, "1")
    assert r.returncode == 0
    assert [(b["bucket"], b["feature"], b["score"], b["eval_failures"]) for b in backlog] == [("refusal", "g", "0", "1")]
    assert cases == []


def test_too_few_rows_exits_1_but_writes(tmp_path):
    r, backlog, _, md = _run(tmp_path, min_rows="50")
    assert r.returncode == 1 and "minimum is 50" in r.stderr
    assert backlog and "INSUFFICIENT DATA" in md


def test_missing_and_invalid_inputs_exit_2(tmp_path):
    assert run_script(SCRIPT, "--min-rows", "5", "--out-dir", str(tmp_path)).returncode == 2
    assert run_script(SCRIPT, "--feedback", str(FX / "feedback.csv"), "--out-dir", str(tmp_path)).returncode == 2
    assert _run(tmp_path, feedback=tmp_path / "nope.csv")[0].returncode == 2
    assert _run(tmp_path, min_rows="ten")[0].returncode == 2
    bad = tmp_path / "bad.csv"
    bad.write_text("id,rating\n1,5\n")
    assert _run(tmp_path, feedback=bad)[0].returncode == 2
