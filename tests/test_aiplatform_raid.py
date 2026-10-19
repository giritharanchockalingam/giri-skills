"""Tests for ai-platform/program-raid-status/scripts/raid_status.py (hand-computed status)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/program-raid-status/scripts/raid_status.py"
FIX = REPO_ROOT / "skills/ai-platform/program-raid-status/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Program manager]"
MH = "id,milestone,baseline_date,forecast_date,duration_days,depends_on,status\n"
RH = "id,type,description,owner,likelihood,impact,due,status,mitigation\n"


def _run(tmp_path: Path, ms: str | Path, raid: str | Path, as_of: str | None = "2026-10-16", *extra: str):
    if isinstance(ms, str):
        (tmp_path / "m.csv").write_text(ms, encoding="utf-8")
        ms = tmp_path / "m.csv"
    if isinstance(raid, str):
        (tmp_path / "r.csv").write_text(raid, encoding="utf-8")
        raid = tmp_path / "r.csv"
    args = ["--milestones", str(ms), "--raid", str(raid), "--out-dir", str(tmp_path / "out"), *extra]
    if as_of is not None:
        args += ["--as-of", as_of]
    res = run_script(SCRIPT, *args)
    j = tmp_path / "out" / "status.json"
    return res, (json.loads(j.read_text(encoding="utf-8")) if j.exists() else None)


def test_fixture_status_and_critical_path(tmp_path):
    res, st = _run(tmp_path, FIX / "milestones.csv", FIX / "raid.csv")
    assert res.returncode == 0, res.stderr
    assert st["critical_path"] == ["M1", "M2", "M3", "M5", "M7"] and st["critical_path_days"] == 85
    assert st["overall_rag"] == "red"
    assert st["top_risks"] == ["R1", "R3", "R2", "R5", "R4"]
    assert st["overdue"] == ["I1", "R1", "D1"]


def test_rag_thresholds_and_boundaries(tmp_path):
    ms = MH + ("A,On plan,2026-11-01,2026-11-01,5,,in_progress\n"
               "B,Ten late,2026-11-01,2026-11-11,5,,in_progress\n"
               "C,Eleven late,2026-11-01,2026-11-12,5,,in_progress\n"
               "D,Early,2026-11-01,2026-10-30,5,,in_progress\n"
               "E,Past forecast,2026-10-10,2026-10-10,5,,in_progress\n"
               "F,Blocked,2026-11-01,2026-11-01,5,,blocked\n"
               "G,Done late,2026-09-01,2026-09-30,5,,done\n")
    res, st = _run(tmp_path, ms, RH)
    rag = {m["id"]: m["rag"] for m in st["milestones"]}
    assert rag == {"A": "green", "B": "amber", "C": "red", "D": "green", "E": "red", "F": "amber", "G": "complete"}
    assert next(m for m in st["milestones"] if m["id"] == "E")["late"] is True


def test_custom_thresholds(tmp_path):
    (tmp_path / "t.csv").write_text("key,value\ngreen_max_slip_days,5\namber_max_slip_days,20\n", encoding="utf-8")
    ms = MH + "A,x,2026-11-01,2026-11-06,5,,in_progress\nB,y,2026-11-01,2026-11-21,5,,in_progress\n"
    res, st = _run(tmp_path, ms, RH, "2026-10-16", "--thresholds", str(tmp_path / "t.csv"))
    assert {m["id"]: m["rag"] for m in st["milestones"]} == {"A": "green", "B": "amber"}


def test_critical_path_tie_breaks_to_lowest_id(tmp_path):
    ms = MH + ("S,Start,2026-11-01,2026-11-01,1,,not_started\n"
               "Y,Branch y,2026-11-01,2026-11-01,4,S,not_started\n"
               "X,Branch x,2026-11-01,2026-11-01,4,S,not_started\n"
               "Z,End,2026-11-01,2026-11-01,2,X|Y,not_started\n")
    res, st = _run(tmp_path, ms, RH)
    assert st["critical_path"] == ["S", "X", "Z"] and st["critical_path_days"] == 7


def test_cycle_exits_1_with_clear_error(tmp_path):
    res, st = _run(tmp_path, FIX / "milestones-cycle.csv", FIX / "raid.csv")
    assert res.returncode == 1 and "dependency cycle" in res.stderr and "M2, M3" in res.stderr
    assert st is None


def test_exposure_overdue_age_and_issue_likelihood(tmp_path):
    raid = ("id,type,description,owner,likelihood,impact,due,status,mitigation,raised\n"
            "I9,issue,Outage,Ops lead,,3,2026-10-06,open,Restore,2026-10-01\n"
            "R9,risk,Drift,,2,2,2026-12-01,open,,2026-10-15\n"
            "R8,risk,Old,Someone,5,5,2026-01-01,closed,,\n")
    res, st = _run(tmp_path, MH + "A,x,2026-11-01,2026-11-01,1,,in_progress\n", raid)
    acts = {a["id"]: a for a in st["raid_actions"]}
    assert set(acts) == {"I9", "R9"}  # closed items excluded
    assert acts["I9"]["exposure"] == 15 and acts["I9"]["overdue_days"] == 10 and acts["I9"]["age_days"] == 15
    assert acts["R9"]["owner"] == TBD and acts["R9"]["next_action"] == "Assign an owner; Define a mitigation"
    assert st["overall_rag"] == "amber"  # overdue but exposure 15 < 20; unowned item


def test_overall_red_from_overdue_high_exposure_only(tmp_path):
    raid = RH + "R1,risk,Big,Owner,4,5,2026-10-15,open,Act\n"
    res, st = _run(tmp_path, MH + "A,x,2026-11-01,2026-11-01,1,,in_progress\n", raid)
    assert st["overall_rag"] == "red" and "R1 (exposure 20) is overdue 1 days" in st["overall_reasons"]


def test_strict_gate(tmp_path):
    res, st = _run(tmp_path, FIX / "milestones.csv", FIX / "raid.csv", "2026-10-16", "--strict")
    assert res.returncode == 1 and (tmp_path / "out" / "status-report.md").exists()
    res2, st2 = _run(tmp_path, FIX / "milestones-green.csv", FIX / "raid-clean.csv", "2026-10-16", "--strict")
    assert res2.returncode == 0 and st2["overall_rag"] == "amber"


def test_as_of_required_and_validated(tmp_path):
    res, _ = _run(tmp_path, FIX / "milestones.csv", FIX / "raid.csv", None)
    assert res.returncode == 2 and "--as-of" in res.stderr
    res, _ = _run(tmp_path, FIX / "milestones.csv", FIX / "raid.csv", "16/10/2026")
    assert res.returncode == 2 and "YYYY-MM-DD" in res.stderr


def test_invalid_inputs_exit_2(tmp_path):
    cases = [
        (MH + "A,x,2026-11-01,2026-11-01,1,B,in_progress\n", RH),                        # unknown dependency
        (MH + "A,x,2026-11-01,2026-11-01,abc,,in_progress\n", RH),                       # bad duration
        (MH + "A,x,2026-11-01,2026-11-01,1,,paused\n", RH),                              # bad status
        (MH + "A,x,2026-11-01,2026-11-01,1,,done\n", RH + "R1,risk,x,o,,3,,open,\n"),    # risk w/o likelihood
        (MH + "A,x,2026-11-01,2026-11-01,1,,done\n", RH + "R1,risk,x,o,6,3,,open,\n"),   # out of range
        ("id,milestone\nA,x\n", RH),                                                      # missing columns
    ]
    for i, (ms, raid) in enumerate(cases):
        sub = tmp_path / f"c{i}"
        sub.mkdir()
        res, _ = _run(sub, ms, raid)
        assert res.returncode == 2, (i, res.stderr)


def test_mermaid_block_and_report_sections(tmp_path):
    res, st = _run(tmp_path, FIX / "milestones.csv", FIX / "raid.csv")
    md = (tmp_path / "out" / "status-report.md").read_text(encoding="utf-8")
    block = md.split("```mermaid\n", 1)[1].split("```", 1)[0]
    for o, c in ("[]", "{}", "()"):
        assert block.count(o) == block.count(c)
    assert "M5 --> M7" in block and "M7 Pilot go-live Customer Operations" in block
    for h in ("## Summary", "## Milestones", "## Critical path", "## Top risks", "## Overdue items",
              "## Decisions needed", "## Method"):
        assert h in md


def test_deterministic_and_verify(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    _run(a, FIX / "milestones.csv", FIX / "raid.csv")
    _run(b, FIX / "milestones.csv", FIX / "raid.csv")
    for name in ("status.csv", "raid-actions.csv", "status-report.md", "status.json"):
        assert (a / "out" / name).read_bytes() == (b / "out" / name).read_bytes(), name
    for name in ("status.csv", "raid-actions.csv"):
        assert run_script(SCRIPT, "--verify", str(a / "out" / name), "--as-of", "2026-10-16").returncode == 0
    p = a / "out" / "status.csv"
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    rows[2]["slip_days"] = "3"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    bad = run_script(SCRIPT, "--verify", str(p), "--as-of", "2026-10-16")
    assert bad.returncode == 1 and "M3" in bad.stderr
