"""Tests for presales/value-case-builder/scripts/value_model.py."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/value-case-builder/scripts/value_model.py"
FX = REPO_ROOT / "skills/presales/value-case-builder/evals/fixtures"


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0 and "benefits.csv" in r.stdout


def test_fixture_model_reconciles_and_traces(tmp_path):
    js, md = tmp_path / "m.json", tmp_path / "v.md"
    r = run_script(SCRIPT, str(FX / "benefits.csv"), str(FX / "costs.csv"), "--discount-rate", "0.08",
                   "--p80-cost-uplift", "0.15", "--client", "Northwind", "--json", str(js), "--out", str(md))
    assert r.returncode == 0, r.stderr
    m = json.loads(js.read_text(encoding="utf-8"))
    yearly = m["yearly"]
    assert len(yearly) == 6 and yearly[0]["benefits"] == 0
    assert round(sum(y["net"] for y in yearly), 2) == m["totals"]["net"]
    assert round(sum(y["costs"] for y in yearly), 2) == m["totals"]["costs"] == 1280000
    # B-01: 18 * 24000 * (25% + 75% + 100% * 3) = 1,728,000
    b1 = next(b for b in m["benefits"] if b["benefit_id"] == "B-01")
    assert b1["total"] == 1728000 and b1["yearly"][1] == 108000
    assert m["totals"]["p80_cost"] == 1472000
    assert m["totals"]["payback_month"] == 25
    assert m["excluded_from_headline"] == ["B-04"] and m["unsourced"] == ["B-04", "C-04"]
    assert [s["benefit_id"] for s in m["sensitivity"]] == ["B-01", "B-02", "B-03"]
    assert m["sensitivity"][0]["net_minus"] == round(m["totals"]["net"] - 0.2 * 1728000, 2)
    text = md.read_text(encoding="utf-8")
    for h in ("## Bottom line", "## Cash flows", "## Sensitivity", "## Sources"):
        assert h in text
    assert "[TO BE BASELINED — owner: Finance lead]" in text  # B-04 and C-04 source
    # every number in the markdown appears in the json (the skill's numbers_trace_to check)
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import check_output
    assert check_output.run_check(f"numbers_trace_to:{js}", str(md), mode="real")["pass"]


def test_no_discount_rate_marks_npv_tbd(tmp_path):
    md = tmp_path / "v.md"
    r = run_script(SCRIPT, str(FX / "benefits.csv"), str(FX / "costs.csv"), "--out", str(md))
    assert r.returncode == 0, r.stderr
    text = md.read_text(encoding="utf-8")
    assert "no sourced discount rate" in text and "no P80 uplift supplied" in text


def test_unbaselined_benefits_withhold_headline(tmp_path):
    md, js = tmp_path / "v.md", tmp_path / "m.json"
    r = run_script(SCRIPT, str(FX / "benefits-unbaselined.csv"), str(FX / "costs.csv"), "--out", str(md), "--json", str(js))
    assert r.returncode == 0, r.stderr
    assert "not a value case yet" in md.read_text(encoding="utf-8")
    assert json.loads(js.read_text())["headline_valid"] is False


def test_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, str(tmp_path / "nope.csv"), str(FX / "costs.csv")).returncode == 1
    bad = tmp_path / "b.csv"
    bad.write_text("benefit_id,name\nB-01,x\n", encoding="utf-8")
    r = run_script(SCRIPT, str(bad), str(FX / "costs.csv"))
    assert r.returncode == 1 and "missing columns" in r.stderr
    nonnum = tmp_path / "n.csv"
    with (FX / "benefits.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    rows[1][3] = "lots"
    with nonnum.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    r = run_script(SCRIPT, str(nonnum), str(FX / "costs.csv"))
    assert r.returncode == 1 and "non-numeric" in r.stderr
    assert run_script(SCRIPT, str(FX / "benefits.csv"), str(FX / "costs.csv"), "--years", "0").returncode == 1
