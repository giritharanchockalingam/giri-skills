"""Tests for ai-platform/ai-postmortem/scripts/postmortem.py (fixtures are fictional: Northwind Billing Assistant)."""
from __future__ import annotations

import csv
import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-postmortem/scripts/postmortem.py"
FX = REPO_ROOT / "skills/ai-platform/ai-postmortem/evals/fixtures"
TBD_IC = "[TO BE BASELINED — owner: Incident commander]"
OUTS = ("postmortem.md", "timings.json", "actions.csv", "eval-cases.csv")


def _run(tmp_path, incident=FX / "incident.csv", timeline=FX / "timeline.csv", factors=None, actions=None,
         strict=False, out="out"):
    o = tmp_path / out
    args = ["--incident", str(incident), "--timeline", str(timeline), "--out-dir", str(o)]
    if factors:
        args += ["--factors", str(factors)]
    if actions:
        args += ["--actions", str(actions)]
    if strict:
        args.append("--strict")
    r = run_script(SCRIPT, *args)
    tj = json.loads((o / "timings.json").read_text(encoding="utf-8")) if (o / "timings.json").exists() else None
    md = (o / "postmortem.md").read_text(encoding="utf-8") if (o / "postmortem.md").exists() else ""
    return r, tj, md, o


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text("# fictional fixture\n" + text, encoding="utf-8")
    return p


def test_timings_hand_computed(tmp_path):
    r, tj, md, _ = _run(tmp_path, factors=FX / "factors.csv", actions=FX / "actions.csv")
    assert r.returncode == 0, r.stderr
    t = tj["timings_min"]
    assert t["time_to_detect"] == 85.0          # 13:40 -> 15:05
    assert t["time_to_acknowledge"] == 15.0     # 15:05 -> 15:20
    assert t["time_to_mitigate"] == 128.0       # 13:40 -> 15:48
    assert t["time_to_resolve"] == 290.0        # 13:40 -> 18:30
    assert t["impact_duration"] == 128.0
    assert tj["status"] == "resolved" and tj["flags"] == []
    assert tj["strict_gate"] == {"pass": True, "reasons": []}


def test_open_incident_and_missing_milestones_not_invented(tmp_path):
    r, tj, md, _ = _run(tmp_path, timeline=FX / "timeline-open.csv")
    assert r.returncode == 0, r.stderr
    assert tj["status"] == "open" and tj["milestones"]["resolved"] is None
    assert tj["timings_min"]["time_to_resolve"] is None
    assert tj["timings_min"]["time_to_acknowledge"] is None
    assert any("listed after a later event" in f for f in tj["flags"])
    assert "OPEN" in md and f"contributing factors {TBD_IC}" in md


def test_out_of_order_milestones_flagged_and_null(tmp_path):
    tl = _write(tmp_path, "tl.csv", "timestamp,event,description,actor_role\n"
                "2026-09-14T15:00:00Z,detected,alert,Support lead\n"
                "2026-09-14T14:50:00Z,acknowledged,page ack,On-call AI engineer\n"
                "2026-09-14T13:00:00Z,mitigated,rollback,On-call AI engineer\n")
    r, tj, md, _ = _run(tmp_path, timeline=tl)
    assert r.returncode == 0, r.stderr
    assert tj["timings_min"]["time_to_acknowledge"] is None      # -10 min -> null
    assert tj["timings_min"]["time_to_mitigate"] is None         # before started_at 13:40
    assert any("out of order: `acknowledged`" in f for f in tj["flags"])
    assert any("before started_at" in f for f in tj["flags"])


def test_coverage_owner_tbd_and_strict_gate(tmp_path):
    r, tj, md, o = _run(tmp_path, factors=FX / "factors.csv", actions=FX / "actions-gaps.csv", strict=True)
    assert r.returncode == 1
    assert tj["uncovered_factors"] == ["F4"] and tj["actions_unowned"] == 1
    rows = list(csv.DictReader((o / "actions.csv").open(encoding="utf-8")))
    a3 = rows[2]
    assert a3["owner"] == TBD_IC and a3["due"] == TBD_IC and a3["status"] == "blocked: no owner"
    # same gaps without --strict: reported, exit 0
    r2, tj2, _, _ = _run(tmp_path, factors=FX / "factors.csv", actions=FX / "actions-gaps.csv", out="o2")
    assert r2.returncode == 0 and tj2["strict_gate"]["pass"] is False


def test_strict_without_factors_fails(tmp_path):
    r, tj, md, _ = _run(tmp_path, strict=True)
    assert r.returncode == 1
    assert "no factors supplied: coverage cannot be shown" in tj["strict_gate"]["reasons"]


def test_blame_phrases_flagged(tmp_path):
    r, tj, md, _ = _run(tmp_path, factors=FX / "factors-blame.csv", actions=FX / "actions.csv")
    assert r.returncode == 0, r.stderr
    assert tj["blame_flags"] == 2
    assert "| factors | F2 evidence | failed to |" in md
    assert "| factors | F3 evidence | Human error |" in md


def test_eval_cases_match_golden_columns_and_only_quoted_inputs(tmp_path):
    r, tj, md, o = _run(tmp_path, factors=FX / "factors.csv", actions=FX / "actions.csv")
    rows = list(csv.DictReader((o / "eval-cases.csv").open(encoding="utf-8")))
    header = (o / "eval-cases.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == ("id,category,difficulty,input,expected,must_contain,must_not_contain,"
                      "expected_json_valid,weight,source,notes")
    assert [r_["input"] for r_ in rows] == ["Can you waive my late fee this month?",
                                             "[TO BE BASELINED — owner: Eval lead]"]
    assert rows[0]["must_contain"] == "" and rows[0]["must_not_contain"] == ""
    assert "timeline row 2" in rows[0]["notes"] and "observed bad output" in rows[0]["notes"]
    # the file feeds llm-eval-harness's build_golden.py unchanged
    g = run_script("skills/ai-platform/llm-eval-harness/scripts/build_golden.py", str(o / "eval-cases.csv"),
                   "--out", str(tmp_path / "golden.csv"))
    assert g.returncode == 0, g.stderr


def test_input_errors_exit_2(tmp_path):
    bad_event = _write(tmp_path, "tl.csv", "timestamp,event,description,actor_role\n2026-09-14T15:00:00Z,paged,x,y\n")
    r, _, _, _ = _run(tmp_path, timeline=bad_event)
    assert r.returncode == 2 and "event must be one of" in r.stderr
    naive = _write(tmp_path, "tl2.csv", "timestamp,event,description,actor_role\n2026-09-14T15:00:00,detected,x,y\n")
    r, _, _, _ = _run(tmp_path, timeline=naive)
    assert r.returncode == 2 and "timezone" in r.stderr
    inc = _write(tmp_path, "inc.csv", "key,value\nid,X\ntitle,T\n")
    r, _, _, _ = _run(tmp_path, incident=inc)
    assert r.returncode == 2 and "started_at" in r.stderr
    sev = _write(tmp_path, "inc2.csv", "key,value\nid,X\ntitle,T\nstarted_at,2026-09-14T13:40:00Z\nseverity,P1\n")
    r, _, _, _ = _run(tmp_path, incident=sev)
    assert r.returncode == 2 and "SEV1-SEV4" in r.stderr
    fac = _write(tmp_path, "f.csv", "factor,category,evidence\nSomething,bad luck,x\n")
    r, _, _, _ = _run(tmp_path, factors=fac)
    assert r.returncode == 2 and "not in the taxonomy" in r.stderr
    empty = _write(tmp_path, "tl3.csv", "timestamp,event,description,actor_role\n")
    r, _, _, _ = _run(tmp_path, timeline=empty)
    assert r.returncode == 2 and "no events" in r.stderr


def test_deterministic_outputs(tmp_path):
    _, _, _, a = _run(tmp_path, factors=FX / "factors-blame.csv", actions=FX / "actions-gaps.csv", out="a")
    _, _, _, b = _run(tmp_path, factors=FX / "factors-blame.csv", actions=FX / "actions-gaps.csv", out="b")
    for name in OUTS:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_verify_passes_and_catches_tampering(tmp_path):
    _, _, _, o = _run(tmp_path, factors=FX / "factors.csv", actions=FX / "actions-gaps.csv")
    for name in OUTS:
        r = run_script(SCRIPT, "--verify", str(o / name))
        assert r.returncode == 0, (name, r.stderr)
    tj = json.loads((o / "timings.json").read_text(encoding="utf-8"))
    tj["timings_min"]["time_to_detect"] = 60.0
    (o / "timings.json").write_text(json.dumps(tj), encoding="utf-8")
    assert run_script(SCRIPT, "--verify", str(o / "timings.json")).returncode == 1
    p = o / "actions.csv"
    p.write_text(p.read_text(encoding="utf-8").replace("blocked: no owner", "open"), encoding="utf-8")
    assert run_script(SCRIPT, "--verify", str(p)).returncode == 1
