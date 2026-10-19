"""Tests for ai-platform/ai-vendor-assessment/scripts/vendor_assess.py (hand-checked scoring)."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-vendor-assessment/scripts/vendor_assess.py"
FIX = REPO_ROOT / "skills/ai-platform/ai-vendor-assessment/evals/fixtures"
PROC = "[TO BE BASELINED — owner: Procurement lead]"


def _run(tmp_path, options: str, criteria: str, risk: str | None = None, *extra):
    (tmp_path / "o.csv").write_text("option,criterion,score,source\n" + options, encoding="utf-8")
    (tmp_path / "c.csv").write_text("criterion,weight,description\n" + criteria, encoding="utf-8")
    args = ["--options", str(tmp_path / "o.csv"), "--criteria", str(tmp_path / "c.csv"),
            "--out-dir", str(tmp_path / "out"), *extra]
    if risk is not None:
        (tmp_path / "r.csv").write_text("option,question_id,answer,evidence\n" + risk, encoding="utf-8")
        args += ["--risk", str(tmp_path / "r.csv")]
    res = run_script(SCRIPT, *args)
    out = tmp_path / "out"
    scores = {r["option"]: r for r in csv.DictReader((out / "scores.csv").open(encoding="utf-8"))} \
        if (out / "scores.csv").exists() else {}
    sens = list(csv.DictReader((out / "sensitivity.csv").open(encoding="utf-8"))) \
        if (out / "sensitivity.csv").exists() else []
    return res, scores, sens


# A: q5 c1; B: q1 c5; weights 51/49 -> A 3.04, B 2.96; quality -20% -> 40.8/49 -> A 2.817, B 3.183 (flip)
FLIP_O = "A,q,5,s\nA,c,1,s\nB,q,1,s\nB,c,5,s\n"
FLIP_C = "q,51,quality\nc,49,cost\n"


def test_weighted_score_normalised(tmp_path):
    res, s, _ = _run(tmp_path, "A,q,4,s\nA,c,2,s\nB,q,3,s\nB,c,3,s\n", "q,3,\nc,1,\n")
    assert res.returncode == 0, res.stderr
    assert s["A"]["weighted_score"] == "3.500" and s["A"]["rank"] == "1"   # 0.75*4 + 0.25*2
    assert s["B"]["weighted_score"] == "3.000" and s["B"]["rank"] == "2"
    assert "Weights sum to 4; normalised to 1.000" in (tmp_path / "out" / "vendor-report.md").read_text(encoding="utf-8")


def test_sensitivity_flip_no_clear_winner(tmp_path):
    res, s, sens = _run(tmp_path, FLIP_O, FLIP_C)
    assert res.returncode == 0                              # not a gate without the flag
    assert s["A"]["weighted_score"] == "3.040" and s["B"]["weighted_score"] == "2.960"
    row = next(r for r in sens if r["criterion"] == "q" and r["change"] == "-20%")
    assert row["top_option"] == "B" and row["top_score"] == "3.183" and row["top_changed"] == "yes"
    rep = (tmp_path / "out" / "vendor-report.md").read_text(encoding="utf-8")
    assert "**No clear winner**" in rep and "q -20%" in rep
    assert "50.0% (2 of 4 runs" in rep                      # q-20% and c+20% flip


def test_require_clear_winner_exits_1(tmp_path):
    res, _, _ = _run(tmp_path, FLIP_O, FLIP_C, None, "--require-clear-winner")
    assert res.returncode == 1
    assert (tmp_path / "out" / "vendor-report.md").exists()


def test_missing_score_incomplete_not_imputed(tmp_path):
    res, s, _ = _run(tmp_path, "A,q,4,s\nA,c,,\nB,q,3,s\nB,c,3,s\n", "q,1,\nc,1,\n")
    assert s["A"]["complete"] == "no" and s["A"]["weighted_score"] == "n/a" and s["A"]["rank"] == "n/a"
    assert s["A"]["missing_criteria"] == f"c {PROC}"
    assert s["B"]["rank"] == "1"
    # option with no row at all for a criterion is also incomplete
    res, s, _ = _run(tmp_path, "A,q,4,s\nB,q,3,s\nB,c,3,s\n", "q,1,\nc,1,\n")
    assert s["A"]["complete"] == "no"


def test_red_flag_rules(tmp_path):
    risk = ("A,TPR-01,yes,dpa\nA,TPR-02,31,policy\nA,TPR-08,29,policy\nA,TPR-09,72,policy\n"
            "B,TPR-01,no,dpa\nB,TPR-02,30,policy\nB,TPR-07,in_progress,letter\nB,TPR-09,unknown,\n")
    res, s, _ = _run(tmp_path, "A,q,5,s\nB,q,4,s\n", "q,1,\n", risk)
    assert s["A"]["red_flags"] == "TPR-01;TPR-02;TPR-08"    # 72h is not > 72
    assert s["B"]["red_flags"] == "none"
    assert "TPR-09" in s["B"]["risk_unanswered"]
    rep = (tmp_path / "out" / "vendor-report.md").read_text(encoding="utf-8")
    assert "has red flags: TPR-01, TPR-02, TPR-08" in rep and "without red flags: B (4.000)" in rep


def test_tie_is_not_clear(tmp_path):
    res, s, _ = _run(tmp_path, "A,q,4,s\nB,q,4,s\n", "q,1,\n")
    assert s["A"]["rank"] == "1" and s["B"]["rank"] == "1"
    assert "tie on weighted score" in (tmp_path / "out" / "vendor-report.md").read_text(encoding="utf-8")


def test_malformed_inputs_exit_2(tmp_path):
    assert _run(tmp_path, "A,q,6,s\n", "q,1,\n")[0].returncode == 2              # score out of range
    assert _run(tmp_path, "A,z,3,s\n", "q,1,\n")[0].returncode == 2              # unknown criterion
    assert _run(tmp_path, "A,q,3,s\nA,q,4,s\n", "q,1,\n")[0].returncode == 2     # duplicate
    assert _run(tmp_path, "A,q,3,s\n", "q,0,\n")[0].returncode == 2              # weights sum 0
    assert _run(tmp_path, "A,q,3,s\n", "q,1,\n", "A,TPR-01,maybe,\n")[0].returncode == 2
    assert _run(tmp_path, "A,q,3,s\n", "q,1,\n", "Z,TPR-01,no,\n")[0].returncode == 2


def test_fixture_happy_path_and_verify(tmp_path):
    outs = []
    for d in ("a", "b"):
        res = run_script(SCRIPT, "--options", str(FIX / "options.csv"), "--criteria", str(FIX / "criteria.csv"),
                         "--risk", str(FIX / "risk.csv"), "--out-dir", str(tmp_path / d))
        assert res.returncode == 0, res.stderr
        outs.append([(tmp_path / d / f).read_bytes() for f in ("scores.csv", "sensitivity.csv", "vendor-report.md")])
    assert outs[0] == outs[1]
    text = (tmp_path / "a" / "scores.csv").read_text(encoding="utf-8")
    assert "Fabrikam AI (fictional),4.150,1,yes,none" in text
    for f in ("scores.csv", "sensitivity.csv"):
        assert run_script(SCRIPT, "--verify", str(tmp_path / "a" / f)).returncode == 0
    bad = tmp_path / "bad.csv"
    bad.write_text(text.replace(f" {PROC}", ""), encoding="utf-8")
    assert run_script(SCRIPT, "--verify", str(bad)).returncode == 1


def test_no_risk_marks_tbd(tmp_path):
    res, s, _ = _run(tmp_path, "A,q,4,s\n", "q,1,\n")
    assert s["A"]["red_flags"] == "not assessed"
    assert "owner: Third-party risk manager" in s["A"]["risk_unanswered"]
    rep = (tmp_path / "out" / "vendor-report.md").read_text(encoding="utf-8")
    assert "red flags not yet assessed" in rep
