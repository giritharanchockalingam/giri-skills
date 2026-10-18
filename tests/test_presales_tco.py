"""Tests for presales/integration-migration-assessor/scripts/tco.py."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/integration-migration-assessor/scripts/tco.py"
FX = REPO_ROOT / "skills/presales/integration-migration-assessor/evals/fixtures"

SCORED = (
    "interface_id,name,band,retire_candidate\n"
    "INT-001,A,Simple,false\nINT-002,B,Medium,false\nINT-003,C,Simple,true\nINT-004,D,Complex,false\n"
)
RATES = (
    "key,value,unit,source\n"
    "currency,USD,,\ncurrent_licence,100000,USD/yr,contract p.1\ncurrent_infrastructure,10000,,bill\n"
    "current_run_team,50000,,CIO\ncurrent_support_contract,5000,,contract\n"
    "target_licence,40000,,quote\ntarget_infrastructure,8000,,memo\ntarget_run_team,30000,,CIO\n"
    "target_support_contract,2000,,quote\nunit_cost_simple,1000,,memo\nunit_cost_medium,3000,,memo\n"
    "unit_cost_complex,9000,,memo\ntraining_one_time,1000,,memo\ndecommission_one_time,500,,memo\n"
    "decommission_month,6,,plan\nhorizon_years,3,,\n"
)


def _files(tmp_path: Path, rates: str = RATES):
    s = tmp_path / "scored.csv"; s.write_text(SCORED, encoding="utf-8")
    r = tmp_path / "rates.csv"; r.write_text(rates, encoding="utf-8")
    return s, r


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_full_rates_compute_totals(tmp_path):
    s, r = _files(tmp_path)
    out, md, js = tmp_path / "tco.csv", tmp_path / "tco.md", tmp_path / "tco.json"
    res = run_script(SCRIPT, str(s), "--rates", str(r), "--out", str(out), "--summary", str(md), "--json", str(js))
    assert res.returncode == 0, res.stderr
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert {"scenario", "category", "line", "year", "amount", "source"} <= set(rows[0])
    assert not any("[TO BE BASELINED" in row["amount"] for row in rows)
    d = json.loads(js.read_text(encoding="utf-8"))
    # retirement candidate excluded: 1 simple + 1 medium + 1 complex = 1000 + 3000 + 9000, + 1000 + 500
    assert d["one_time_total"] == 14500
    assert d["run_rate"]["current"]["1"] == 165000 and d["run_rate"]["target"]["3"] == 80000
    # dual run: 6 months of current run-rate in year 1 only
    assert d["run_rate"]["target"]["1"] == 80000 + 82500
    assert d["payback_year"] == 2
    text = md.read_text(encoding="utf-8")
    assert "## Run-rate comparison" in text and "## Net benefit and payback" in text


def test_missing_prices_become_tbd_not_numbers(tmp_path):
    s, r = _files(tmp_path, "key,value\ncurrency,USD\ndecommission_month,6\n")
    out, js = tmp_path / "tco.csv", tmp_path / "tco.json"
    res = run_script(SCRIPT, str(s), "--rates", str(r), "--out", str(out), "--json", str(js))
    assert res.returncode == 0, res.stderr
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert all(row["amount"].startswith("[TO BE BASELINED") for row in rows)
    d = json.loads(js.read_text(encoding="utf-8"))
    assert d["one_time_total"] is None and d["net_3yr"] is None and d["payback_year"] is None


def test_fixture_runs(tmp_path):
    scored = tmp_path / "scored.csv"
    sc = run_script("skills/presales/integration-migration-assessor/scripts/score_inventory.py",
                    str(FX / "inventory.csv"), "--out", str(scored))
    assert sc.returncode == 0, sc.stderr
    res = run_script(SCRIPT, str(scored), "--rates", str(FX / "rates.csv"), "--out", str(tmp_path / "t.csv"))
    assert res.returncode == 0, res.stderr


def test_bad_input_exits_1(tmp_path):
    s, r = _files(tmp_path)
    assert run_script(SCRIPT, str(tmp_path / "nope.csv"), "--rates", str(r), "--out", str(tmp_path / "t.csv")).returncode == 1
    bad = tmp_path / "bad.csv"; bad.write_text("key,value\ncurrent_licence,lots\n", encoding="utf-8")
    res = run_script(SCRIPT, str(s), "--rates", str(bad), "--out", str(tmp_path / "t.csv"))
    assert res.returncode == 1 and "non-numeric" in res.stderr
    noband = tmp_path / "nb.csv"; noband.write_text("interface_id,name\nI,x\n", encoding="utf-8")
    assert run_script(SCRIPT, str(noband), "--rates", str(r), "--out", str(tmp_path / "t.csv")).returncode == 1
