"""Tests for assess.py --previous (re-check after a data fix)."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/data-readiness-assessment/scripts/assess.py"
FIX = REPO_ROOT / "skills/ai-platform/data-readiness-assessment/evals/fixtures"


def _run(out, data, reqs="requirements.csv", *extra):
    return run_script(SCRIPT, "--data", str(FIX / data), "--requirements", str(FIX / reqs), "--as-of", "2026-10-01",
                      "--out-dir", str(out), *extra)


def test_previous_fixture_is_real_output(tmp_path):
    assert _run(tmp_path, "orders-defects.csv").returncode == 1
    fresh = json.loads((tmp_path / "readiness.json").read_text(encoding="utf-8"))
    stored = json.loads((FIX / "previous-readiness.json").read_text(encoding="utf-8"))
    stored.pop("_note")
    assert fresh == stored


def test_fix_is_shown(tmp_path):
    r = _run(tmp_path, "orders-sample.csv", "requirements.csv", "--previous", str(FIX / "previous-readiness.json"))
    assert r.returncode == 0, r.stderr
    pv = json.loads((tmp_path / "readiness.json").read_text(encoding="utf-8"))["previous"]
    assert (pv["verdict_was"], pv["verdict_now"]) == ("Not ready", "Ready")
    assert pv["fixed"] == ["volume", "completeness", "uniqueness", "duplicates", "freshness"] and pv["regressed"] == []
    assert pv["notes"] == []
    md = (tmp_path / "readiness.md").read_text(encoding="utf-8")
    assert "| schema | pass | pass | 4 | 4 | unchanged |" in md


def test_regression_and_requirements_change(tmp_path):
    first = tmp_path / "first"
    assert _run(first, "orders-sample.csv").returncode == 0
    r = _run(tmp_path / "second", "orders-defects.csv", "requirements-partial.csv", "--previous",
             str(first / "readiness.json"))
    pv = json.loads((tmp_path / "second" / "readiness.json").read_text(encoding="utf-8"))["previous"]
    assert r.returncode in (0, 1)
    assert pv["regressed"] and all(d["change"] in ("regressed", "now TBD", "unchanged") for d in pv["dimensions"])
    assert any(d["change"] == "now TBD" for d in pv["dimensions"])
    assert pv["notes"] == ["The requirements differ between the two assessments; verdicts are not like for like."]


def test_newly_scored_transition():
    import importlib.util
    spec = importlib.util.spec_from_file_location("assess", REPO_ROOT / SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m._transition("TBD", "fail") == "newly scored (fail)"
    assert m._transition("TBD", "pass") == "newly scored (pass)"
    assert m._transition(None, "pass") == "not assessed before"


def test_bad_previous_exits_2(tmp_path):
    (tmp_path / "bad.json").write_text(json.dumps({"verdict": "Ready"}), encoding="utf-8")
    r = _run(tmp_path / "o", "orders-sample.csv", "requirements.csv", "--previous", str(tmp_path / "bad.json"))
    assert r.returncode == 2 and "must be a readiness.json" in r.stderr
    r = _run(tmp_path / "o", "orders-sample.csv", "requirements.csv", "--previous", str(tmp_path / "none.json"))
    assert r.returncode == 2 and "previous assessment not found" in r.stderr
