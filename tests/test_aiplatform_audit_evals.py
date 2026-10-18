"""Tests for ai-platform/eval-engineering-runner/scripts/audit_evals.py (and check_jsonl.py)."""
from __future__ import annotations

import json
import re

from conftest import REPO_ROOT, run_script

SKILL = "skills/ai-platform/eval-engineering-runner"
SCRIPT = f"{SKILL}/scripts/audit_evals.py"
CHECK = f"{SKILL}/scripts/check_jsonl.py"
FIXTURE = REPO_ROOT / SKILL / "evals" / "fixtures" / "eval-set.jsonl"


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def _run(tmp_path, dataset, targets=None, *extra):
    out = tmp_path / "out"
    args = ["--dataset", str(dataset), "--out-dir", str(out), *extra]
    if targets:
        args += ["--targets", str(targets)]
    r = run_script(SCRIPT, *args)
    audit = json.loads((out / "eval-audit.json").read_text(encoding="utf-8")) if (out / "eval-audit.json").exists() else None
    return r, audit, out


def _cov(audit, cat):
    return next(c for c in audit["coverage"] if c["category"] == cat)


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_fixture_counts_hand_checked(tmp_path):
    t = _write(tmp_path, "t.csv", "category,min_cases\nbilling,5\nrefunds,4\naccount,4\nsafety,3\n")
    r, a, out = _run(tmp_path, FIXTURE, t)
    assert r.returncode == 0, r.stderr
    assert (a["verdict"], a["rows_in"], a["rows_clean"], a["rows_dropped"]) == ("PASS", 20, 18, 2)
    # billing 7 raw: b6 is a duplicate input (dropped) -> 6; refunds 5 raw: r5 empty reference -> 4
    assert (_cov(a, "billing")["raw_rows"], _cov(a, "billing")["clean_cases"]) == (7, 6)
    assert (_cov(a, "refunds")["raw_rows"], _cov(a, "refunds")["clean_cases"]) == (5, 4)
    assert _cov(a, "billing")["share_pct"] == 33.3                   # 6 / 18
    assert a["issue_counts"] == {"conflicting_reference": 1, "empty_reference": 1, "missing_grader": 1,
                                 "near_duplicate": 1, "split_leakage": 1}
    assert a["balance"] == {"categories": 4, "max_cases": 6, "min_cases": 4, "max_to_min_ratio": 1.5}


def test_clean_file_is_valid_and_deduped(tmp_path):
    _, _, out = _run(tmp_path, FIXTURE)
    lines = [json.loads(x) for x in (out / "eval-clean.jsonl").read_text(encoding="utf-8").splitlines()]
    ids = [x["id"] for x in lines]
    assert len(lines) == 18 and "b6" not in ids and "r5" not in ids and "b7" in ids
    assert run_script(CHECK, str(out / "eval-clean.jsonl"), "--require", "id", "--require", "input").returncode == 0


def test_below_target_fails_with_exact_gap(tmp_path):
    t = _write(tmp_path, "t.csv", "category,min_cases\nsafety,6\nescalations,2\n")
    r, a, out = _run(tmp_path, FIXTURE, t)
    assert r.returncode == 1 and a["verdict"] == "FAIL"
    assert (_cov(a, "safety")["gap"], _cov(a, "escalations")["gap"]) == (2, 2)
    assert _cov(a, "billing")["status"] == "NO TARGET"
    md = (out / "eval-audit.md").read_text(encoding="utf-8")
    assert "add 2 distinct case(s) to reach min_cases 6" in md


def test_no_targets_is_not_gated_with_owned_tbd(tmp_path):
    r, a, out = _run(tmp_path, FIXTURE)
    assert r.returncode == 0 and a["verdict"] == "NOT GATED"
    md = (out / "eval-audit.md").read_text(encoding="utf-8")
    assert "[TO BE BASELINED — owner: Eval owner]" in md
    for h in ("## Verdict", "## Coverage", "## Quality issues", "## Recommendations"):
        assert h in md


def test_csv_with_tags_and_reference_free_grader(tmp_path):
    ds = _write(tmp_path, "d.csv",
                "id,prompt,reference,tags,grader_type\n"
                "1,Hello there,hi,greet;smalltalk,exact\n"
                "2,Rate this essay,,writing,rubric\n"
                "1,Goodbye now,bye,greet,exact\n"
                ",Thanks a lot,welcome,greet,\n")
    _, a, out = _run(tmp_path, ds)
    assert a["rows_clean"] == 4                                       # rubric row kept without reference
    assert _cov(a, "greet")["clean_cases"] == 3 and _cov(a, "smalltalk")["clean_cases"] == 1
    kinds = a["issue_counts"]
    assert kinds["duplicate_id"] == 1 and kinds["missing_id"] == 1 and kinds["missing_grader"] == 1
    ids = [json.loads(x)["id"] for x in (out / "eval-clean.jsonl").read_text(encoding="utf-8").splitlines()]
    assert ids == ["1", "2", "1-dup2", "row-5"]


def test_exact_duplicate_same_reference_is_dropped(tmp_path):
    ds = _write(tmp_path, "d.jsonl",
                '{"id":"a","input":"What is 2+2?","expected":"4","category":"math"}\n'
                '{"id":"b","input":"what is 2 + 2","expected":"4","category":"math"}\n')
    _, a, _ = _run(tmp_path, ds)
    assert a["rows_clean"] == 1 and a["issue_counts"] == {"duplicate": 1, "missing_grader": 1}


def test_near_dup_threshold_is_a_parameter(tmp_path):
    ds = _write(tmp_path, "d.jsonl",
                '{"id":"a","input":"reset my account password","expected":"x","category":"c","grader":"contains"}\n'
                '{"id":"b","input":"reset my account password now","expected":"x","category":"c","grader":"contains"}\n')
    _, a, _ = _run(tmp_path, ds)                                       # Jaccard 4/5 = 0.8 < 0.9
    assert "near_duplicate" not in a["issue_counts"]
    _, a, _ = _run(tmp_path, ds, None, "--near-dup-threshold", "0.8")
    assert a["issue_counts"]["near_duplicate"] == 1 and a["near_dup_threshold"] == 0.8


def test_missing_required_columns_exit_1(tmp_path):
    ds = _write(tmp_path, "d.csv", "id,input\n1,hello\n")
    r, a, _ = _run(tmp_path, ds)
    assert r.returncode == 1 and "lacks required column" in a["error"]


def test_missing_files_exit_2(tmp_path):
    assert run_script(SCRIPT, "--dataset", str(tmp_path / "x.jsonl"), "--out-dir", str(tmp_path / "o")).returncode == 2
    assert run_script(SCRIPT, "--dataset", str(FIXTURE), "--targets", str(tmp_path / "t.csv"),
                      "--out-dir", str(tmp_path / "o")).returncode == 2


def test_check_jsonl_rejects_duplicates(tmp_path):
    p = _write(tmp_path, "c.jsonl", '{"id":"a","input":"x"}\n{"id":"a","input":"y"}\n')
    assert run_script(CHECK, str(p), "--require", "input").returncode == 1


def test_fixtures_are_labelled_fictional():
    fx = REPO_ROOT / SKILL / "evals" / "fixtures"
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        assert "fictional fixture" in json.loads(line)["notes"]
    for f in fx.glob("*.csv"):
        for line in f.read_text(encoding="utf-8").splitlines()[1:]:
            assert "fictional fixture" in line


def test_scripts_have_no_network_or_subprocess():
    for f in (REPO_ROOT / SKILL / "scripts").glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(socket|urllib|requests|http|subprocess)\b", src, re.M), f
