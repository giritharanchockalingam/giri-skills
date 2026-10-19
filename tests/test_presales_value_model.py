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


def test_bad_input_exits_2(tmp_path):
    # was exit 1; audit 2026-10-19 aligned input errors with the repo convention (exit 2)
    assert run_script(SCRIPT, str(tmp_path / "nope.csv"), str(FX / "costs.csv")).returncode == 2
    bad = tmp_path / "b.csv"
    bad.write_text("benefit_id,name\nB-01,x\n", encoding="utf-8")
    r = run_script(SCRIPT, str(bad), str(FX / "costs.csv"))
    assert r.returncode == 2 and "missing columns" in r.stderr
    nonnum = tmp_path / "n.csv"
    with (FX / "benefits.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    rows[1][3] = "lots"
    with nonnum.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    r = run_script(SCRIPT, str(nonnum), str(FX / "costs.csv"))
    assert r.returncode == 2 and "non-numeric" in r.stderr
    assert run_script(SCRIPT, str(FX / "benefits.csv"), str(FX / "costs.csv"), "--years", "0").returncode == 2


# --- regression tests for audit 2026-10-19 findings -------------------------------------------

B_HDR = "benefit_id,name,driver,unit_value,units_per_year,ramp_pct_y1,ramp_pct_y2,ramp_pct_y3,source\n"
AUDIT_COSTS = ("cost_id,name,one_time,run_rate_per_year,start_year,source\n"
               "K-1,Build,900000,,0,estimate v1\nK-2,Cloud run,,120000,1,FinOps quote\nK-3,Training,60000,,1,\n")
AUDIT_BENEFITS = B_HDR + (
    'V-1,Agent handle-time reduction,Contact centre labour,"$4.20","120,000",30,80,100,Ops dashboard FY26\n'
    "V-2,Retired middleware licence,Licence,450000,1,0,100,100,Contract renewal letter\n"
    "V-3,Fewer escalations,Tier-2 cost,85,6000,,,,Support lead email\n"
    "V-4,Revenue uplift,Conversion,,,,,,\n"
)
TBD = "[TO BE BASELINED — owner: Finance lead]"


def _w(tmp_path: Path, name: str, text: str, newline: str = "\n") -> Path:
    p = tmp_path / name
    p.write_text(text.replace("\n", newline), encoding="utf-8")
    return p


def test_audit_blank_row_of_commas_is_skipped(tmp_path):
    """Finding (high): ',,,,' row crashed rendering with a TypeError traceback."""
    b = _w(tmp_path, "b.csv", B_HDR + ",,,,,,,,\nV-1,a,b,10,100,100,100,100,s\n")
    c = _w(tmp_path, "c.csv", AUDIT_COSTS)
    js = tmp_path / "m.json"
    r = run_script(SCRIPT, str(b), str(c), "--json", str(js), "--out", str(tmp_path / "v.md"))
    assert r.returncode == 0, r.stderr
    m = json.loads(js.read_text(encoding="utf-8"))
    assert [x["benefit_id"] for x in m["benefits"]] == ["V-1"]
    # trailing blank CRLF row too
    b2 = _w(tmp_path, "b2.csv", B_HDR + "V-1,a,b,10,100,100,100,100,s\n,,,,,,,,\n", newline="\r\n")
    assert run_script(SCRIPT, str(b2), str(c)).returncode == 0


def test_audit_blank_id_on_data_row_exits_2(tmp_path):
    b = _w(tmp_path, "b.csv", B_HDR + ",a,b,10,100,100,100,100,s\n")
    r = run_script(SCRIPT, str(b), str(_w(tmp_path, "c.csv", AUDIT_COSTS)))
    assert r.returncode == 2 and "blank benefit_id" in r.stderr and "Traceback" not in r.stderr


def test_audit_blank_ramp_is_tbd_not_100pct(tmp_path):
    """Finding (medium): blank ramps defaulted to 100% and V-3 was counted at full value."""
    js, md = tmp_path / "m.json", tmp_path / "v.md"
    r = run_script(SCRIPT, str(_w(tmp_path, "b.csv", AUDIT_BENEFITS)), str(_w(tmp_path, "c.csv", AUDIT_COSTS)),
                   "--discount-rate", "0.1", "--json", str(js), "--out", str(md))
    assert r.returncode == 0, r.stderr
    m = json.loads(js.read_text(encoding="utf-8"))
    v3 = next(b for b in m["benefits"] if b["benefit_id"] == "V-3")
    assert v3["ramp_pct"] == [None, None, None] and v3["ramp_tbd"] is True
    assert v3["in_headline"] is False and v3["total"] is None
    assert "V-3" in m["excluded_from_headline"]
    assert m["totals"]["benefits"] == 3866400  # V-1 + V-2 only; no 2,550,000 from V-3
    text = md.read_text(encoding="utf-8")
    assert "100%/100%/100%" not in text
    v3_line = next(ln for ln in text.splitlines() if ln.startswith("| V-3 "))
    assert TBD in v3_line
    v4_line = next(ln for ln in text.splitlines() if ln.startswith("| V-4 "))
    assert "100%" not in v4_line


def test_audit_partial_blank_ramp_marked(tmp_path):
    b = _w(tmp_path, "b.csv", B_HDR + "V-1,a,b,10,100,25,,100,s\n")
    js, md = tmp_path / "m.json", tmp_path / "v.md"
    r = run_script(SCRIPT, str(b), str(_w(tmp_path, "c.csv", AUDIT_COSTS)), "--json", str(js), "--out", str(md))
    assert r.returncode == 0, r.stderr
    assert json.loads(js.read_text())["benefits"][0]["in_headline"] is False
    assert f"25%/—/100% (blank ramp {TBD})" in md.read_text(encoding="utf-8")
    # a 1-year horizon only needs the year-1 ramp
    r = run_script(SCRIPT, str(b), str(_w(tmp_path, "c.csv", AUDIT_COSTS)), "--years", "1", "--json", str(js))
    assert r.returncode == 0 and json.loads(js.read_text())["benefits"][0]["total"] == 250


def test_audit_duplicate_benefit_id_exits_2(tmp_path):
    """Finding (medium): duplicate V-1 rows were both counted in the headline."""
    b = _w(tmp_path, "b.csv", B_HDR + "V-1,a,b,10,100,100,100,100,s\nV-1,a,b,10,100,100,100,100,s\n", newline="\r\n")
    r = run_script(SCRIPT, str(b), str(_w(tmp_path, "c.csv", AUDIT_COSTS)))
    assert r.returncode == 2 and "duplicate benefit_id 'V-1'" in r.stderr
    c = _w(tmp_path, "c2.csv", AUDIT_COSTS + "K-1,Again,1,,0,x\n")
    r = run_script(SCRIPT, str(_w(tmp_path, "b2.csv", AUDIT_BENEFITS)), str(c))
    assert r.returncode == 2 and "duplicate cost_id 'K-1'" in r.stderr


def test_audit_non_utf8_and_overflow_exit_2_without_traceback(tmp_path):
    """Finding (medium): binary file -> UnicodeDecodeError; 1e400 one_time -> AssertionError."""
    binf = tmp_path / "bin.csv"
    binf.write_bytes(b"\x7fELF\x02\x01\x01\x00" + bytes(range(128, 256)) * 4)
    c = _w(tmp_path, "c.csv", AUDIT_COSTS)
    r = run_script(SCRIPT, str(binf), str(c))
    assert r.returncode == 2 and "not a UTF-8 CSV" in r.stderr and "Traceback" not in r.stderr
    b = _w(tmp_path, "b.csv", AUDIT_BENEFITS)
    c5 = _w(tmp_path, "c5.csv", "cost_id,name,one_time,run_rate_per_year,start_year,source\nK1,x,1e400,,0,s\n")
    r = run_script(SCRIPT, str(b), str(c5))
    assert r.returncode == 2 and "not a finite number" in r.stderr and "Traceback" not in r.stderr
    big = _w(tmp_path, "c6.csv", "cost_id,name,one_time,run_rate_per_year,start_year,source\n"
             "K1,x,1e308,,0,s\nK2,y,1e308,,0,s\n")
    r = run_script(SCRIPT, str(b), str(big))
    assert r.returncode == 2 and "too large" in r.stderr and "Traceback" not in r.stderr


def test_audit_fractional_start_year_exits_2(tmp_path):
    """Finding (low): start_year '1.9' was truncated to 1 with exit 0."""
    c4 = _w(tmp_path, "c4.csv", "cost_id,name,one_time,run_rate_per_year,start_year,source\nK1,x,500000,,1.9,s\n")
    r = run_script(SCRIPT, str(_w(tmp_path, "b.csv", AUDIT_BENEFITS)), str(c4))
    assert r.returncode == 2 and "start_year must be a whole year" in r.stderr
    ok = _w(tmp_path, "c5.csv", "cost_id,name,one_time,run_rate_per_year,start_year,source\nK1,x,500000,,2.0,s\n")
    assert run_script(SCRIPT, str(_w(tmp_path, "b.csv", AUDIT_BENEFITS)), str(ok)).returncode == 0
