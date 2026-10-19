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


# ---------------------------------------------------------------- audit 2026-10-19 regressions

AUDIT_MS = (MH.rstrip("\n") + ",owner\n"
            "A,Use-case sign-off,2026-08-01,2026-08-01,10,,done,PO\n"
            "B,Data pipeline,2026-09-01,2026-09-20,30,A,in_progress,Data lead\n"
            "C,Model eval harness,2026-09-15,2026-09-18,15,A,in_progress,\n"
            "D,Security review,2026-10-01,2026-10-01,5,A,blocked,CISO\n"
            "E,Pilot launch,2026-11-02,2026-11-09,10,B|C|D,not_started,PM\n"
            'F,"=HYPERLINK(""http://x"",""Training"")",2026-10-30,2026-10-30,40,A,in_progress,HR\n')
AUDIT_RAID = (RH.rstrip("\n") + ",raised\n"
              "R1,risk,Vendor API rate limits,Platform lead,4,5,2026-10-10,open,Negotiate quota,2026-09-01\n"
              "R2,risk,Low adoption,,2,3,2026-11-30,open,,2026-09-10\n"
              'I1,issue,GPU quota exhausted,Infra lead,,4,2026-10-12,open,"=HYPERLINK(""http://evil"",""Click"")",2026-10-01\n'
              "D1,dependency,Legal approval of DPA,Legal,,,2026-10-05,open,Chase legal,2026-09-01\n"
              "A1,assumption,Users have SSO,IT,,,,open,Check with IT,\n"
              "R3,risk,Old risk,Owner,5,5,2026-09-01,closed,,\n")


def test_audit_zero_open_raid_items_is_valid(tmp_path):
    ms = MH.rstrip("\n") + ",owner\nA,x,2026-11-01,2026-11-01,5,,in_progress,PM\n"
    raid = RH + "R9,risk,old,Owner,2,2,2026-09-01,closed,done\n"
    res, st = _run(tmp_path, ms, raid, "2026-10-15")
    assert res.returncode == 0 and st["overall_rag"] == "green" and st["raid_actions"] == []
    acts = tmp_path / "out" / "raid-actions.csv"
    assert acts.read_text(encoding="utf-8").count("\n") == 1  # header only
    v = run_script(SCRIPT, "--verify", str(acts), "--as-of", "2026-10-15")
    assert v.returncode == 0, v.stderr
    # status.csv with no rows is still invalid
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "status.csv").write_text("id,milestone,baseline,forecast,slip_days,rag,on_critical_path,status\n",
                                               encoding="utf-8")
    assert run_script(SCRIPT, "--verify", str(tmp_path / "s" / "status.csv")).returncode == 1


def test_audit_zero_open_raid_items_run_skill_exits_0(tmp_path):
    (tmp_path / "m.csv").write_text(MH.rstrip("\n") + ",owner\nA,x,2026-11-01,2026-11-01,5,,in_progress,PM\n",
                                    encoding="utf-8")
    (tmp_path / "r.csv").write_text(RH + "R9,risk,old,Owner,2,2,2026-09-01,closed,done\n", encoding="utf-8")
    r = run_script("scripts/run_skill.py", "ai-platform/program-raid-status", "--input", f"raid={tmp_path / 'r.csv'}",
                   "--input", f"milestones={tmp_path / 'm.csv'}", "--input", "as_of=2026-10-15", "--provider", "none",
                   "--out", str(tmp_path / "run"))
    assert r.returncode == 0, r.stdout + r.stderr


def test_audit_raid_verify_flags_blank_next_action(tmp_path):
    p = tmp_path / "raid-actions.csv"
    p.write_text("id,type,exposure,owner,due,overdue_days,age_days,next_action\nR1,risk,4,O,2026-10-20,0,,\n",
                 encoding="utf-8")
    v = run_script(SCRIPT, "--verify", str(p), "--as-of", "2026-10-15")
    assert v.returncode == 1 and "next_action" in v.stderr


def test_audit_csv_injection_escaped(tmp_path):
    res, st = _run(tmp_path, AUDIT_MS, AUDIT_RAID, "2026-10-15")
    assert res.returncode == 0
    status = {r["id"]: r for r in csv.DictReader((tmp_path / "out/status.csv").open(encoding="utf-8"))}
    assert status["F"]["milestone"] == "'=HYPERLINK(\"http://x\",\"Training\")"
    assert status["B"]["slip_days"] == "19"
    acts = list(csv.DictReader((tmp_path / "out/raid-actions.csv").open(encoding="utf-8")))
    for r in acts:
        for v in r.values():
            assert not v.startswith(("=", "+", "-", "@", "\t", "\r"))
    for f in ("status.csv", "raid-actions.csv"):
        assert run_script(SCRIPT, "--verify", str(tmp_path / "out" / f), "--as-of", "2026-10-15").returncode == 0
    # a formula as the whole next_action is escaped
    raid = RH + 'X1,risk,r,O,2,2,2026-12-01,open,"=1+1"\n'
    res2, st2 = _run(tmp_path, AUDIT_MS, raid, "2026-10-15")
    row = list(csv.DictReader((tmp_path / "out/raid-actions.csv").open(encoding="utf-8")))[0]
    assert row["next_action"] == "'=1+1"


def test_audit_critical_path_tie_marks_all_zero_float(tmp_path):
    res, st = _run(tmp_path, AUDIT_MS, AUDIT_RAID, "2026-10-15")
    assert st["critical_path"] == ["A", "B", "E"] and st["critical_path_days"] == 50
    assert st["critical_path_ties"] == ["F"]
    cp = {m["id"]: m["on_critical_path"] for m in st["milestones"]}
    assert cp == {"A": "yes", "B": "yes", "C": "no", "D": "no", "E": "yes", "F": "yes"}
    assert "Tie: F also has zero float" in (tmp_path / "out/status-report.md").read_text(encoding="utf-8")


def test_audit_non_utf8_input_exit_2_no_traceback(tmp_path):
    bad = tmp_path / "bin.csv"
    bad.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\xff\xfe\xfd")
    res, _ = _run(tmp_path, AUDIT_MS, bad, "2026-10-15")
    assert res.returncode == 2 and "Traceback" not in res.stderr and "UTF-8" in res.stderr
    cp = tmp_path / "cp.csv"
    cp.write_bytes(MH.encode() + b"A,Caf\xe9,2026-11-01,2026-11-01,5,,in_progress\n")
    res2, _ = _run(tmp_path, cp, RH, "2026-10-15")
    assert res2.returncode == 2 and "Traceback" not in res2.stderr
