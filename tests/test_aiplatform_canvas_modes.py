"""Tests for canvas.py --previous (re-review of an existing canvas)."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-use-case-canvas/scripts/canvas.py"
FX = REPO_ROOT / "skills/ai-platform/ai-use-case-canvas/evals/fixtures"


def test_previous_shows_then_vs_now(tmp_path):
    r = run_script(SCRIPT, str(FX / "answers.json"), "--previous", str(FX / "previous-score.json"),
                   "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    dec = (tmp_path / "decision.md").read_text(encoding="utf-8")
    assert "## Changes since last review" in dec
    assert "| data readiness | 2 | 3 | +1 |" in dec and "| value | 3 | 3 | same |" in dec
    assert "| priority | 8.0 | 12.0 | +4.00 |" in dec
    assert "| decision | wait | build | changed |" in dec
    prev = json.loads((tmp_path / "score.json").read_text(encoding="utf-8"))["previous"]
    assert prev["verdict"] == {"was": "Proceed after data readiness", "now": "Proceed to design", "changed": True}


def test_without_previous_output_unchanged(tmp_path):
    r = run_script(SCRIPT, str(FX / "answers.json"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "Changes since last review" not in (tmp_path / "decision.md").read_text(encoding="utf-8")
    assert "previous" not in json.loads((tmp_path / "score.json").read_text(encoding="utf-8"))


def test_axis_blank_now_is_not_carried_over(tmp_path):
    r = run_script(SCRIPT, str(FX / "answers-no-data-readiness.json"), "--out-dir", str(tmp_path / "first"))
    assert r.returncode == 0, r.stderr
    earlier = json.loads((tmp_path / "first" / "score.json").read_text(encoding="utf-8"))
    earlier["scores"]["data_readiness"] = 4
    earlier["priority"] = 9.0
    (tmp_path / "prev.json").write_text(json.dumps(earlier), encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "answers-no-data-readiness.json"), "--previous", str(tmp_path / "prev.json"),
                   "--out-dir", str(tmp_path / "second"))
    assert r.returncode == 0, r.stderr
    dec = (tmp_path / "second" / "decision.md").read_text(encoding="utf-8")
    assert "| data readiness | 4 | [TO BE BASELINED — owner: Legal Ops Lead] | no longer scored |" in dec
    assert "not comparable" in dec


def test_previous_for_another_use_case_rejected(tmp_path):
    prev = json.loads((FX / "previous-score.json").read_text(encoding="utf-8"))
    prev["name"] = "Invoice triage"
    (tmp_path / "prev.json").write_text(json.dumps(prev), encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "answers.json"), "--previous", str(tmp_path / "prev.json"), "--out-dir", str(tmp_path))
    assert r.returncode == 1 and "not 'Benefits enquiry assistant'" in r.stderr


def test_previous_not_a_score_file_rejected(tmp_path):
    (tmp_path / "prev.json").write_text(json.dumps({"name": "Benefits enquiry assistant"}), encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "answers.json"), "--previous", str(tmp_path / "prev.json"), "--out-dir", str(tmp_path))
    assert r.returncode == 1 and "not a canvas score.json" in r.stderr
    (tmp_path / "bad.json").write_text(json.dumps({"name": "Benefits enquiry assistant", "verdict": "Park",
                                                    "scores": {"value": 9}}), encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "answers.json"), "--previous", str(tmp_path / "bad.json"), "--out-dir", str(tmp_path))
    assert r.returncode == 1 and "scores.value" in r.stderr
