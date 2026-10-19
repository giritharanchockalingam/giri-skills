"""Tests for agreement.py --previous (round-over-round comparison)."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/annotation-agreement/scripts/agreement.py"
FIX = REPO_ROOT / "skills/ai-platform/annotation-agreement/evals/fixtures"
OUTS = ("agreement.json", "disputed-items.csv", "label-agreement.csv", "agreement-report.md")


def _run(tmp_path, labels="labels.csv", *extra):
    return run_script(SCRIPT, "--labels", str(FIX / labels), "--guidelines", str(FIX / "guidelines.md"),
                      "--out-dir", str(tmp_path), *extra)


def test_previous_fixture_is_real_output_of_round1(tmp_path):
    r = _run(tmp_path, "labels-round1.csv")
    assert r.returncode == 0, r.stderr
    fresh = json.loads((tmp_path / "agreement.json").read_text(encoding="utf-8"))
    stored = json.loads((FIX / "previous-agreement.json").read_text(encoding="utf-8"))
    stored.pop("_note")
    assert fresh == stored


def test_previous_round_section_and_verify(tmp_path):
    r = _run(tmp_path, "labels.csv", "--previous", str(FIX / "previous-agreement.json"))
    assert r.returncode == 0, r.stderr
    md = (tmp_path / "agreement-report.md").read_text(encoding="utf-8")
    assert md.index("## Change since previous round") < md.index("## Method & limits")
    assert "alpha improved (0.321 → 0.595)" in md
    assert "| Krippendorff's alpha | 0.321 | 0.595 | +0.274 |" in md
    assert "| refund_request | 0.400 | 0.727 | +0.327 |" in md
    doc = json.loads((tmp_path / "agreement.json").read_text(encoding="utf-8"))
    assert doc["previous_round"]["source"] == "previous-agreement.json"
    for name in OUTS:
        v = run_script(SCRIPT, "--verify", str(tmp_path / name), "--labels", str(FIX / "labels.csv"))
        assert v.returncode == 0, v.stdout


def test_declined_labels_named(tmp_path):
    # compare the other way round: the pilot against the later round, so every label falls
    first = tmp_path / "later"
    assert _run(first, "labels.csv").returncode == 0
    r = _run(tmp_path / "out", "labels-round1.csv", "--previous", str(first / "agreement.json"))
    assert r.returncode == 0, r.stderr
    md = (tmp_path / "out" / "agreement-report.md").read_text(encoding="utf-8")
    assert "alpha declined (0.595 → 0.321)" in md
    assert "Labels whose agreement fell: `billing_dispute`, `other`, `payment_failed`, `refund_request`" in md


def test_without_previous_report_unchanged(tmp_path):
    assert _run(tmp_path, "labels.csv").returncode == 0
    assert "Change since previous round" not in (tmp_path / "agreement-report.md").read_text(encoding="utf-8")
    assert "previous_round" not in json.loads((tmp_path / "agreement.json").read_text(encoding="utf-8"))


def test_unusable_previous_exits_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"status": "insufficient", "krippendorff_alpha": None, "label_agreement": []}),
                   encoding="utf-8")
    r = _run(tmp_path / "o", "labels.csv", "--previous", str(bad))
    assert r.returncode == 2 and "no agreement score" in r.stderr
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"alpha": 0.5}), encoding="utf-8")
    r = _run(tmp_path / "o", "labels.csv", "--previous", str(other))
    assert r.returncode == 2 and "must be an agreement.json" in r.stderr
