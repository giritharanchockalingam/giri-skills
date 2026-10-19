"""Tests for vendor_assess.py --previous (re-assessment against an earlier scores.csv)."""
from __future__ import annotations

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-vendor-assessment/scripts/vendor_assess.py"
FIX = REPO_ROOT / "skills/ai-platform/ai-vendor-assessment/evals/fixtures"


def _base(tmp_path, *extra):
    return run_script(SCRIPT, "--options", str(FIX / "options.csv"), "--criteria", str(FIX / "criteria.csv"),
                      "--risk", str(FIX / "risk.csv"), "--out-dir", str(tmp_path / "out"), *extra)


def test_previous_adds_changes_section(tmp_path):
    r = _base(tmp_path, "--previous", str(FIX / "previous-scores.csv"))
    assert r.returncode == 0, r.stderr
    rep = (tmp_path / "out" / "vendor-report.md").read_text(encoding="utf-8")
    assert rep.index("## Changes since last assessment") < rep.index("## Method")
    assert "| Fabrikam AI (fictional) | 3.900 | 4.150 | +0.250 | 2 | 1 | none | none |" in rep
    assert "| Build in-house | n/a | 3.250 | new option | — | 3 |" in rep
    assert "New red flags: Tailspin Models (fictional) (TPR-02)" in rep


def test_scores_csv_unchanged_by_previous(tmp_path):
    assert _base(tmp_path / "a").returncode == 0
    assert _base(tmp_path / "b", "--previous", str(FIX / "previous-scores.csv")).returncode == 0
    a = (tmp_path / "a" / "out" / "scores.csv").read_text(encoding="utf-8")
    b = (tmp_path / "b" / "out" / "scores.csv").read_text(encoding="utf-8")
    assert a == b
    assert "Changes since last assessment" not in (tmp_path / "a" / "out" / "vendor-report.md").read_text(encoding="utf-8")


def test_risk_not_assessed_is_not_compared(tmp_path):
    r = run_script(SCRIPT, "--options", str(FIX / "options.csv"), "--criteria", str(FIX / "criteria.csv"),
                   "--previous", str(FIX / "previous-scores.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    rep = (tmp_path / "vendor-report.md").read_text(encoding="utf-8")
    assert "not comparable (risk not assessed then or now)" in rep and "New red flags: none." in rep


def test_cleared_flag_is_listed(tmp_path):
    prev = tmp_path / "prev.csv"
    prev.write_text("option,weighted_score,rank,complete,red_flags,missing_criteria,risk_unanswered\n"
                    "Fabrikam AI (fictional),4.000,1,yes,TPR-05;TPR-08,none,none\n", encoding="utf-8")
    r = _base(tmp_path, "--previous", str(prev))
    assert r.returncode == 0, r.stderr
    assert "| Fabrikam AI (fictional) | 4.000 | 4.150 | +0.150 | 1 | 1 | none | TPR-05, TPR-08 |" in \
        (tmp_path / "out" / "vendor-report.md").read_text(encoding="utf-8")


def test_bad_previous_exits_2(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("option,score\nX,1\n", encoding="utf-8")
    r = _base(tmp_path, "--previous", str(bad))
    assert r.returncode == 2 and "previous scores: missing column(s)" in r.stderr
    dup = tmp_path / "dup.csv"
    dup.write_text("option,weighted_score,rank,complete,red_flags,missing_criteria,risk_unanswered\n"
                   "A,4,1,yes,none,none,none\nA,3,2,yes,none,none,none\n", encoding="utf-8")
    r = _base(tmp_path, "--previous", str(dup))
    assert r.returncode == 2 and "duplicate option" in r.stderr
