"""presales/account-plan: quarterly refresh (--previous-plays / --previous-pipeline)."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/account-plan"
SCRIPT = SK / "scripts/account_plan.py"
FX = SK / "evals/fixtures"


def plan(tmp_path, *extra, pipeline=FX / "pipeline.csv"):
    out, plays = tmp_path / "plan.md", tmp_path / "plays.csv"
    r = run_script(SCRIPT, str(FX / "stakeholders.csv"), str(pipeline), str(FX / "services.csv"),
                   "--out", str(out), "--plays", str(plays), "--client", "Northwind", "--as-of", "2026-10-01", *extra)
    rows = list(csv.DictReader(plays.open(encoding="utf-8"))) if plays.exists() else []
    return r, (out.read_text(encoding="utf-8") if out.exists() else ""), rows


def test_play_outcomes_and_carried_owner(tmp_path):
    r, md, rows = plan(tmp_path, "--previous-plays", str(FX / "plays-previous.csv"))
    assert r.returncode == 0, r.stderr
    assert "| P1 | Open white space: Data and AI | carried over as P1 |" in md
    assert "| P2 | Open white space: API platform engineering | done |" in md
    assert "| P4 | Re-establish contact with Raj Patel (VP Supply Chain) | closed by events" in md
    by = {x["play"]: x for x in rows}
    assert by["Move Dana Ortiz (CFO) from stance -1 to +1"]["owner"] == "Priya (last quarter's owner — confirm)"
    assert "(carried from P3, last quarter)" in by["Move Dana Ortiz (CFO) from stance -1 to +1"]["addresses"]
    assert by["Cover departure risk: Lee Wong (VP Apps)"]["owner"].startswith("[TO BE BASELINED")
    assert "New this quarter:" in md and "fictional" not in md


def test_pipeline_delta(tmp_path):
    r, md, _ = plan(tmp_path, "--previous-pipeline", str(FX / "pipeline-previous.csv"))
    assert r.returncode == 0, r.stderr
    assert "| Apigee platform readiness | added | qualify |" in md
    assert "| Legacy EDI support renewal | removed (won, lost or merged — confirm) | was negotiate |" in md
    assert "close_date 2026-10-31 → 2026-11-15" in md
    assert "| Last quarter | Play | Outcome |" not in md          # no plays file given -> no plays table


def test_no_previous_no_section(tmp_path):
    _, md, _ = plan(tmp_path)
    assert "## Since last plan" not in md


def test_bad_previous_status_and_columns_fail(tmp_path):
    bad = tmp_path / "prev.csv"
    bad.write_text("play_id,play,status\nP1,Open white space: Data and AI,maybe\n", encoding="utf-8")
    r, _, _ = plan(tmp_path, "--previous-plays", str(bad))
    assert r.returncode == 1 and "status must be done | open | dropped" in r.stderr
    nocol = tmp_path / "nocol.csv"
    nocol.write_text("id,text\n1,x\n", encoding="utf-8")
    r, _, _ = plan(tmp_path, "--previous-pipeline", str(nocol))
    assert r.returncode == 1 and "missing columns" in r.stderr
