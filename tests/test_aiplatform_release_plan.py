"""Tests for ai-platform/ai-release-plan/scripts/release_plan.py (fixtures are fictional)."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-release-plan/scripts/release_plan.py"
FX = REPO_ROOT / "skills/ai-platform/ai-release-plan/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Release manager]"


def _run(tmp_path, facts=None, gates=None):
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--facts", str(facts or FX / "facts.csv"), "--gates", str(gates or FX / "gates.csv"),
                   "--out-dir", str(out))
    plan = json.loads((out / "gates.json").read_text(encoding="utf-8")) if (out / "gates.json").exists() else None
    md = (out / "release-plan.md").read_text(encoding="utf-8") if (out / "release-plan.md").exists() else ""
    return r, plan, md


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text("# fictional fixture\n" + text, encoding="utf-8")
    return p


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_happy_path_stages_durations_and_gates(tmp_path):
    r, plan, md = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert plan["first_stage_ready"] is True
    # medium tier policy: 5, 25, 50
    assert plan["canary_steps_pct"] == [5, 25, 50]
    ids = [s["id"] for s in plan["stages"]]
    assert ids == ["offline_eval", "shadow", "canary_1", "canary_2", "canary_3", "ga"]
    # hand-checked: 2000 req at 48000/day -> shadow 2000/(2000/h)=1h; 5% -> 100/h -> 20h; 25% -> 500/h -> 4h; 50% -> 2h
    hours = {s["id"]: s["min_duration_hours"] for s in plan["stages"]}
    assert hours == {"offline_eval": None, "shadow": 1, "canary_1": 20, "canary_2": 4, "canary_3": 2, "ga": None}
    assert all(g["status"] == "met" for g in plan["gates"])
    # 6 live-stage bounds -> 5 gate rows outside offline_eval, each one bound
    assert len(plan["rollback_triggers"]) == 5
    assert {"stage": "ga", "metric": "eval_pass_rate", "condition": "< 0.9", "threshold": 0.9} in plan["rollback_triggers"]
    for sec in ("## Readiness", "## Stages", "## Gates", "## Rollback", "## Owners"):
        assert sec in md


def test_missing_owners_are_tbd_with_role(tmp_path):
    _, plan, md = _run(tmp_path)
    assert plan["owners"]["Release manager"] == TBD and plan["owners"]["Product owner"] == TBD
    assert plan["owners"]["Eval lead"] == "Eval Lead (fictional)"
    assert "owner: ___" not in md and "[TO BE BASELINED]" not in md


def test_first_stage_gate_not_met_exits_1_but_writes_plan(tmp_path):
    r, plan, md = _run(tmp_path, facts=FX / "facts-eval-below-gate.csv")
    assert r.returncode == 1 and "eval_pass_rate" in r.stderr
    assert plan["first_stage_ready"] is False and plan["first_stage_blockers"] == ["eval_pass_rate"]
    assert "NOT READY" in md and "| offline_eval | eval_pass_rate | >= 0.9 | 0.82 | NOT MET |" in md


def test_no_offline_gate_is_a_blocker(tmp_path):
    gates = _write(tmp_path, "g.csv", "stage,metric,min,max\nshadow,error_rate,,0.01\n")
    r, plan, _ = _run(tmp_path, gates=gates)
    assert r.returncode == 1
    assert plan["first_stage_blockers"] == ["no offline_eval gate supplied"]


def test_unmeasured_metric_is_not_met(tmp_path):
    gates = _write(tmp_path, "g.csv", "stage,metric,min,max\noffline_eval,toxicity_rate,,0.01\n")
    r, plan, _ = _run(tmp_path, gates=gates)
    assert r.returncode == 1
    assert plan["gates"][0]["status"] == "not measured" and plan["gates"][0]["actual"] is None


def test_high_tier_policy_and_override(tmp_path):
    base = (FX / "facts.csv").read_text(encoding="utf-8")
    high = _write(tmp_path, "high.csv", base.replace("risk_tier,medium", "risk_tier,high"))
    _, plan, _ = _run(tmp_path, facts=high)
    assert plan["canary_steps_pct"] == [1, 5, 10, 25, 50]
    # 1% of 48000/day = 20/h -> 2000/20 = 100h
    assert plan["stages"][2]["min_duration_hours"] == 100
    over = _write(tmp_path, "over.csv", base + "canary_steps,2;20,fixture,fictional fixture\n")
    _, plan2, _ = _run(tmp_path, facts=over)
    assert plan2["canary_steps_pct"] == [2, 20] and "override" in plan2["canary_steps_basis"]


def test_missing_traffic_makes_duration_tbd(tmp_path):
    base = (FX / "facts.csv").read_text(encoding="utf-8")
    facts = _write(tmp_path, "f.csv", "\n".join(ln for ln in base.splitlines() if not ln.startswith("daily_requests")) + "\n")
    r, plan, md = _run(tmp_path, facts=facts)
    assert r.returncode == 0
    assert plan["stages"][1]["min_duration_hours"] is None
    assert f"| 2 | Shadow | 100 | no | {TBD} |" in md


def test_missing_and_invalid_inputs_exit_2(tmp_path):
    assert run_script(SCRIPT, "--facts", str(FX / "facts.csv"), "--out-dir", str(tmp_path)).returncode == 2
    r = run_script(SCRIPT, "--facts", str(tmp_path / "nope.csv"), "--gates", str(FX / "gates.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 2
    bad_tier = _write(tmp_path, "t.csv", "key,value\nsystem_name,X\nrisk_tier,extreme\n")
    assert _run(tmp_path, facts=bad_tier)[0].returncode == 2
    empty_gates = _write(tmp_path, "e.csv", "stage,metric,min,max\n")
    r2 = _run(tmp_path, gates=empty_gates)[0]
    assert r2.returncode == 2 and "never defaulted" in r2.stderr
    no_bound = _write(tmp_path, "nb.csv", "stage,metric,min,max\noffline_eval,eval_pass_rate,,\n")
    assert _run(tmp_path, gates=no_bound)[0].returncode == 2
