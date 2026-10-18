"""Tests for ai-platform/bias-fairness-check/scripts/fairness.py.

Expected numbers are hand-computed from the fixture (fictional):
  A: TP4 FN1 FP1 TN4 (n10)  B: TP2 FN2 FP1 TN5 (n10)  C: TP1 TN2 (n3)
"""
from __future__ import annotations

import json

import pytest

from conftest import REPO_ROOT, run_script

SKILL = "skills/ai-platform/bias-fairness-check"
SCRIPT = f"{SKILL}/scripts/fairness.py"
FX = REPO_ROOT / SKILL / "evals" / "fixtures"
TBB = "[TO BE BASELINED — owner: Responsible AI lead]"


def _run(tmp_path, *extra):
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--predictions", str(FX / "predictions.csv"), *extra, "--out", str(out))
    data = json.loads((out / "fairness.json").read_text()) if (out / "fairness.json").exists() else None
    md = (out / "fairness-report.md").read_text() if (out / "fairness-report.md").exists() else ""
    return r, data, md


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_per_group_rates_hand_checked(tmp_path):
    r, d, _ = _run(tmp_path, "--thresholds", str(FX / "thresholds.csv"), "--reference-group", "A")
    assert r.returncode == 0, r.stderr
    a, b, c = d["groups"]["A"], d["groups"]["B"], d["groups"]["C"]
    assert (a["n"], a["base_rate"], a["selection_rate"], a["accuracy"]) == (10, 0.5, 0.5, 0.8)
    assert (a["tpr"], a["fpr"], a["precision"]) == (0.8, 0.2, 0.8)
    assert (b["n"], b["base_rate"], b["selection_rate"], b["accuracy"]) == (10, 0.4, 0.3, 0.7)
    assert (b["tpr"], b["fpr"], b["precision"]) == (0.5, 0.1667, 0.6667)
    assert (c["n"], c["selection_rate"], c["tpr"], c["fpr"], c["precision"]) == (3, 0.3333, 1.0, 0.0, 1.0)
    assert b["dir_vs_reference"] == 0.6 and c["dir_vs_reference"] == 0.6667
    assert a["mean_score"] == 0.5  # 5 x 0.8 + 5 x 0.2 over 10


def test_fairness_metrics_hand_checked(tmp_path):
    _, d, _ = _run(tmp_path, "--thresholds", str(FX / "thresholds.csv"), "--reference-group", "A")
    m = {k: v["value"] for k, v in d["metrics"].items()}
    assert m == {"demographic_parity_difference": 0.2, "disparate_impact_ratio": 0.6,
                 "equal_opportunity_difference": 0.5, "equalized_odds_difference": 0.5}
    assert d["verdict"] == "PASS" and d["breaches"] == []


def test_four_fifths_breach_exits_1_and_writes_outputs(tmp_path):
    r, d, md = _run(tmp_path, "--thresholds", str(FX / "thresholds-four-fifths.csv"), "--reference-group", "A")
    assert r.returncode == 1
    assert d["verdict"] == "FAIL" and d["breaches"] == ["disparate_impact_ratio"]
    assert d["metrics"]["disparate_impact_ratio"]["status"] == "breach"
    assert "four-fifths rule" in md and "**FAIL**" in md


def test_no_thresholds_is_incomplete_not_pass(tmp_path):
    r, d, md = _run(tmp_path)
    assert r.returncode == 0
    assert d["verdict"] == "INCOMPLETE"
    assert all(v["status"] == "to_be_baselined" and v["owner"] == "Responsible AI lead" for v in d["metrics"].values())
    assert TBB in md and "pass |" not in md


def test_partial_thresholds(tmp_path):
    _, d, _ = _run(tmp_path, "--thresholds", str(FX / "thresholds-partial.csv"), "--reference-group", "A")
    assert d["metrics"]["demographic_parity_difference"]["status"] == "pass"
    assert d["metrics"]["disparate_impact_ratio"]["status"] == "to_be_baselined"
    assert d["verdict"] == "INCOMPLETE"


def test_default_reference_is_highest_selection_rate(tmp_path):
    _, d, md = _run(tmp_path)
    assert d["reference_group"] == "A" and "highest selection rate" in d["reference_basis"]
    assert "highest selection rate" in md


def test_min_sample_flags_small_group(tmp_path):
    _, d, md = _run(tmp_path, "--min-sample", "5")
    assert d["small_groups"] == ["C"] and d["groups"]["C"]["small_sample"] is True
    assert "`C`" in md.split("## Small groups")[1]


def test_min_sample_absent_is_to_be_baselined(tmp_path):
    _, d, md = _run(tmp_path)
    assert d["small_groups"] == []
    assert TBB in md.split("## Small groups")[1].split("## Limits")[0]


def test_named_sensitive_attribute(tmp_path):
    out = tmp_path / "o"
    r = run_script(SCRIPT, "--predictions", str(FX / "predictions-region.csv"), "--sensitive-attr", "region",
                   "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert json.loads((out / "fairness.json").read_text())["sensitive_attribute"] == "region"


def test_missing_column_exits_2(tmp_path):
    r = run_script(SCRIPT, "--predictions", str(FX / "predictions-region.csv"), "--out", str(tmp_path / "o"))
    assert r.returncode == 2 and "group" in r.stderr


def test_missing_file_exits_2(tmp_path):
    assert run_script(SCRIPT, "--predictions", str(tmp_path / "nope.csv")).returncode == 2
    assert run_script(SCRIPT).returncode == 2  # argparse: required option


def test_non_binary_label_exits_2(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("group,label,prediction\nA,1,1\nB,maybe,0\n")
    r = run_script(SCRIPT, "--predictions", str(p))
    assert r.returncode == 2 and "not binary" in r.stderr


def test_unknown_metric_exits_2(tmp_path):
    t = tmp_path / "t.csv"
    t.write_text("metric,threshold\naccuracy_gap,0.1\n")
    r = run_script(SCRIPT, "--predictions", str(FX / "predictions.csv"), "--thresholds", str(t))
    assert r.returncode == 2 and "unknown metric" in r.stderr


def test_single_group_exits_2(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("group,label,prediction\nA,1,1\nA,0,0\n")
    assert run_script(SCRIPT, "--predictions", str(p)).returncode == 2


def test_undefined_tpr_excluded_and_named(tmp_path):
    p = tmp_path / "p.csv"
    # group B has no actual positives -> TPR undefined; EOD uses A only -> fewer than 2 -> undefined
    p.write_text("group,label,prediction\nA,1,1\nA,0,0\nB,0,1\nB,0,0\n")
    t = tmp_path / "t.csv"
    t.write_text("metric,threshold\nequal_opportunity_difference,0.1\n")
    r = run_script(SCRIPT, "--predictions", str(p), "--thresholds", str(t), "--json")
    d = json.loads(r.stdout)
    assert d["groups"]["B"]["tpr"] is None
    assert d["metrics"]["equal_opportunity_difference"]["status"] == "undefined"
    assert any("no actual positives" in n for n in d["notes"])
    # equalised odds still defined from the FPR gap: A FPR 0, B FPR 0.5
    assert d["metrics"]["equalized_odds_difference"]["value"] == 0.5


def test_custom_positive_label(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("group,label,prediction\nA,approve,approve\nA,deny,deny\nB,approve,deny\nB,deny,deny\n")
    r = run_script(SCRIPT, "--predictions", str(p), "--positive-label", "approve", "--json")
    d = json.loads(r.stdout)
    assert d["groups"]["A"]["selection_rate"] == 0.5 and d["groups"]["B"]["selection_rate"] == 0.0
    assert d["metrics"]["disparate_impact_ratio"]["value"] == 0.0


@pytest.mark.parametrize("alias", ["equalised_odds_difference"])
def test_british_spelling_alias(tmp_path, alias):
    t = tmp_path / "t.csv"
    t.write_text(f"metric,threshold\n{alias},0.4\n")
    r = run_script(SCRIPT, "--predictions", str(FX / "predictions.csv"), "--thresholds", str(t), "--json")
    assert r.returncode == 1  # 0.5 > 0.4
    assert json.loads(r.stdout)["breaches"] == ["equalized_odds_difference"]
