"""Tests for fairness.py --previous (periodic re-check against an earlier fairness.json)."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/bias-fairness-check/scripts/fairness.py"
FIX = REPO_ROOT / "skills/ai-platform/bias-fairness-check/evals/fixtures"


def _run(out, preds="predictions.csv", *extra):
    return run_script(SCRIPT, "--predictions", str(FIX / preds), "--thresholds", str(FIX / "thresholds.csv"),
                      "--reference-group", "A", "--min-sample", "5", "--out", str(out), *extra)


def test_previous_fixture_is_real_output(tmp_path):
    r = _run(tmp_path, "predictions-previous.csv")
    assert r.returncode == 1  # last quarter breached
    fresh = json.loads((tmp_path / "fairness.json").read_text(encoding="utf-8"))
    stored = json.loads((FIX / "previous-fairness.json").read_text(encoding="utf-8"))
    stored.pop("_note")
    assert fresh == stored


def test_resolved_breaches_and_group_change(tmp_path):
    r = _run(tmp_path, "predictions.csv", "--previous", str(FIX / "previous-fairness.json"))
    assert r.returncode == 0, r.stderr
    pv = json.loads((tmp_path / "fairness.json").read_text(encoding="utf-8"))["previous"]
    assert pv["verdict_was"] == "FAIL" and pv["verdict_now"] == "PASS"
    assert pv["new_breaches"] == [] and len(pv["resolved_breaches"]) == 4
    assert pv["metrics"]["disparate_impact_ratio"] == {"was": 0.2, "now": 0.6, "change": 0.4,
                                                       "status_was": "breach", "status_now": "pass"}
    assert pv["groups"]["B"]["change"] == 0.2
    md = (tmp_path / "fairness-report.md").read_text(encoding="utf-8")
    assert md.index("## Change since last check") < md.index("## Limits")


def test_new_breach_reported(tmp_path):
    first = tmp_path / "first"
    assert _run(first).returncode == 0
    r = _run(tmp_path / "second", "predictions-previous.csv", "--previous", str(first / "fairness.json"))
    assert r.returncode == 1
    pv = json.loads((tmp_path / "second" / "fairness.json").read_text(encoding="utf-8"))["previous"]
    assert "disparate_impact_ratio" in pv["new_breaches"] and pv["resolved_breaches"] == []
    assert "New breaches: `demographic_parity_difference`" in (tmp_path / "second" / "fairness-report.md").read_text(encoding="utf-8")


def test_reference_change_noted_and_groups_presence(tmp_path):
    prev = json.loads((FIX / "previous-fairness.json").read_text(encoding="utf-8"))
    prev["reference_group"] = "B"
    prev["groups"]["D"] = dict(prev["groups"]["C"])
    (tmp_path / "prev.json").write_text(json.dumps(prev), encoding="utf-8")
    r = _run(tmp_path / "o", "predictions.csv", "--previous", str(tmp_path / "prev.json"))
    assert r.returncode == 0, r.stderr
    pv = json.loads((tmp_path / "o" / "fairness.json").read_text(encoding="utf-8"))["previous"]
    assert pv["groups"]["D"]["presence"] == "absent this window" and pv["groups"]["D"]["change"] is None
    assert any("Reference group changed from 'B' to 'A'" in n for n in pv["notes"])


def test_other_attribute_or_bad_file_exits_2(tmp_path):
    prev = json.loads((FIX / "previous-fairness.json").read_text(encoding="utf-8"))
    prev["sensitive_attribute"] = "region"
    (tmp_path / "prev.json").write_text(json.dumps(prev), encoding="utf-8")
    r = _run(tmp_path / "o", "predictions.csv", "--previous", str(tmp_path / "prev.json"))
    assert r.returncode == 2 and "not comparable" in r.stderr
    (tmp_path / "bad.json").write_text("{}", encoding="utf-8")
    r = _run(tmp_path / "o", "predictions.csv", "--previous", str(tmp_path / "bad.json"))
    assert r.returncode == 2 and "must be a fairness.json" in r.stderr
