"""Tests for presales/account-plan/scripts/account_plan.py."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/account-plan/scripts/account_plan.py"
FX = REPO_ROOT / "skills/presales/account-plan/evals/fixtures"


def run(tmp_path, stk=None, pipe=None, svc=None, *extra):
    out, plays = tmp_path / "ap.md", tmp_path / "plays.csv"
    r = run_script(SCRIPT, str(stk or FX / "stakeholders.csv"), str(pipe or FX / "pipeline.csv"),
                   str(svc or FX / "services.csv"), "--out", str(out), "--plays", str(plays), *extra)
    return r, out, plays


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_plan_from_fixtures(tmp_path):
    r, out, plays = run(tmp_path, None, None, None, "--client", "Northwind", "--as-of", "2026-10-01")
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "| 5 | — | Dana Ortiz | — | — | Maria Chen |" in text         # influence x stance grid
    assert "| Lee Wong ⚠ |" in text
    assert "| Data and AI | none | P1 |" in text and "| Integration modernization | active | — |" in text
    assert "| **Total** | | 1,652,000 (excludes 1 unvalued) |" in text
    assert "| Apigee platform readiness | qualify | [TO BE BASELINED — owner: ___] |" in text
    rows = list(csv.DictReader(plays.open(encoding="utf-8")))
    kinds = {r_["type"] for r_ in rows}
    assert kinds == {"white-space", "stakeholder", "risk", "coverage"}
    assert sum(r_["type"] == "white-space" for r_ in rows) == 2
    assert any("Dana Ortiz" in r_["play"] and r_["type"] == "stakeholder" for r_ in rows)   # stance -1, influence 5
    assert not any("Sam Kim" in r_["play"] and r_["type"] == "stakeholder" for r_ in rows)  # influence 2
    assert all(r_["owner"] == "[TO BE BASELINED — owner: ___]" for r_ in rows)
    assert any("Sam Kim" in r_["play"] and r_["type"] == "coverage" for r_ in rows)      # never contacted


def test_without_as_of_no_staleness_and_default_play(tmp_path):
    r, out, plays = run(tmp_path, None, FX / "pipeline-thin.csv")
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader(plays.open(encoding="utf-8")))
    assert not any(r_["type"] == "coverage" for r_ in rows)
    assert "excludes 1 unvalued" in out.read_text(encoding="utf-8")
    quiet = tmp_path / "q.csv"
    quiet.write_text("name,role,stance,influence,last_contact,departure_risk\nA,CTO,2,5,,no\n", encoding="utf-8")
    svc = tmp_path / "s.csv"
    svc.write_text("service,status_at_account\nX,active\n", encoding="utf-8")
    r, out, plays = run(tmp_path, quiet, None, svc)
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader(plays.open(encoding="utf-8")))
    assert len(rows) == 1 and rows[0]["type"] == "posture"


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.csv")[0].returncode == 1
    bad = tmp_path / "b.csv"
    bad.write_text("name,role,stance,influence,last_contact,departure_risk\nA,CTO,7,5,,no\n", encoding="utf-8")
    r = run(tmp_path, bad)[0]
    assert r.returncode == 1 and "stance" in r.stderr
    svc = tmp_path / "s.csv"
    svc.write_text("service,status_at_account\nX,maybe\n", encoding="utf-8")
    assert run(tmp_path, None, None, svc)[0].returncode == 1
    pipe = tmp_path / "p.csv"
    pipe.write_text("opportunity,stage,value,close_date,owner,next_step\nO,qualify,lots,,,\n", encoding="utf-8")
    assert run(tmp_path, None, pipe)[0].returncode == 1
    assert run(tmp_path, None, None, None, "--as-of", "yesterday")[0].returncode == 1
