"""Tests for ai-platform/ai-adoption-and-literacy/scripts/adoption_plan.py (hand-computed totals)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-adoption-and-literacy/scripts/adoption_plan.py"
FIX = REPO_ROOT / "skills/ai-platform/ai-adoption-and-literacy/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Change lead]"
CATALOG = (
    "module_id,title,hours,audience,level,format,mandatory_for\n"
    "M-A,Basics,1,user|operator|overseer,1,e-learning,\n"
    "M-B,Practice,2.5,user|operator,2,lab,\n"
    "M-O,Oversight,2,overseer,2,workshop,overseer\n"
)


def _run(tmp_path: Path, pop: str | Path, *extra: str, catalog: str | None = CATALOG):
    if isinstance(pop, str):
        (tmp_path / "pop.csv").write_text(pop, encoding="utf-8")
        pop = tmp_path / "pop.csv"
    args = ["--population", str(pop), "--out-dir", str(tmp_path / "out"), *extra]
    if catalog is not None:
        (tmp_path / "cat.csv").write_text(catalog, encoding="utf-8")
        args += ["--catalog", str(tmp_path / "cat.csv")]
    res = run_script(SCRIPT, *args)
    j = tmp_path / "out" / "adoption.json"
    return res, (json.loads(j.read_text(encoding="utf-8")) if j.exists() else None)


POP = ("role,headcount,exposure,proficiency,business_unit\n"
       "Agent,10,user,0,Ops\n"
       "Lead,2,overseer,3,Ops\n"
       "Analyst,4,operator,1,Tech\n")


def test_rule_level_above_proficiency_and_hours(tmp_path):
    res, plan = _run(tmp_path, POP)
    assert res.returncode == 0, res.stderr
    roles = {r["role"]: r for r in plan["roles"]}
    assert roles["Agent"]["modules"] == ["M-A", "M-B"] and roles["Agent"]["hours_per_person"] == 3.5
    assert roles["Agent"]["total_hours"] == 35.0
    assert roles["Analyst"]["modules"] == ["M-B"] and roles["Analyst"]["total_hours"] == 10.0  # level 1 not > 1
    assert plan["totals"]["training_hours"] == 49.0  # 35 + 10 + 2*2


def test_overseer_always_gets_mandatory_module(tmp_path):
    res, plan = _run(tmp_path, POP)
    lead = next(r for r in plan["roles"] if r["role"] == "Lead")
    assert lead["modules"] == ["M-O"]  # proficiency 3 but mandatory_for overseer
    rows = list(csv.DictReader((tmp_path / "out" / "curriculum.csv").open(encoding="utf-8")))
    assert any(r["role"] == "Lead" and "mandatory for overseer" in r["reason"] for r in rows)


def test_seats_per_module(tmp_path):
    res, plan = _run(tmp_path, POP)
    seats = {m["module_id"]: m["seats"] for m in plan["modules"]}
    assert seats == {"M-A": 10, "M-B": 14, "M-O": 2}


def test_default_catalog_fixture_totals(tmp_path):
    res, plan = _run(tmp_path, FIX / "population.csv", "--waves", str(FIX / "waves.csv"), catalog=None)
    assert res.returncode == 0, res.stderr
    assert plan["totals"]["people"] == 221 and plan["totals"]["training_hours"] == 812.5
    load = {r["business_unit"]: r for r in csv.DictReader((tmp_path / "out" / "training-load.csv").open(encoding="utf-8"))}
    assert load["Customer Operations"]["hours"] == "558" and load["Finance"]["hours"] == "112.5"
    assert load["Technology"]["wave"] == "1"
    assert "this skill's own curriculum design" in (tmp_path / "out" / "adoption-plan.md").read_text(encoding="utf-8")


def test_missing_waves_and_targets_are_tbd_with_owner(tmp_path):
    res, plan = _run(tmp_path, POP)
    md = (tmp_path / "out" / "adoption-plan.md").read_text(encoding="utf-8")
    assert all(k["target"] == TBD for k in plan["kpis"])
    assert all(e["wave"] == TBD for e in plan["training_load"])
    assert "TO BE BASELINED ]" not in md and "owner: ]" not in md


def test_targets_used_verbatim(tmp_path):
    (tmp_path / "t.csv").write_text("key,value,source\nweekly_active_rate,0.55,plan v2\n", encoding="utf-8")
    res, plan = _run(tmp_path, POP, "--targets", str(tmp_path / "t.csv"))
    k = {x["kpi"]: x for x in plan["kpis"]}
    assert k["weekly_active_rate"]["target"] == "0.55" and k["weekly_active_rate"]["target_source"] == "plan v2"
    assert k["task_success_rate"]["target"] == TBD


def test_strict_gate_operator_without_module(tmp_path):
    pop = "role,headcount,exposure,proficiency,business_unit\nOps,3,operator,3,Tech\n"
    res, plan = _run(tmp_path, pop)
    assert res.returncode == 0
    res, plan = _run(tmp_path, pop, "--strict")
    assert res.returncode == 1 and plan["gate"] == "fail"
    assert "Ops (Tech)" in plan["gaps"]["unmapped_operator_overseer_roles"]


def test_strict_fails_when_catalog_has_no_oversight_module(tmp_path):
    cat = "module_id,title,hours,audience,level,format\nM-A,Basics,1,overseer,1,e-learning\n"
    pop = "role,headcount,exposure,proficiency,business_unit\nLead,2,overseer,0,Ops\n"
    res, plan = _run(tmp_path, pop, "--strict", catalog=cat)
    assert res.returncode == 1 and plan["gaps"]["overseer_rule_unmet"] is True


def test_invalid_inputs_exit_2(tmp_path):
    bad = [
        "role,headcount,exposure,proficiency,business_unit\nA,5,superuser,1,Ops\n",   # bad exposure
        "role,headcount,exposure,proficiency,business_unit\nA,5,user,4,Ops\n",        # proficiency > 3
        "role,headcount,exposure,business_unit\nA,5,user,Ops\n",                       # missing column
        "role,headcount,exposure,proficiency,business_unit\n",                         # empty
        "role,headcount,exposure,proficiency,business_unit\nA,5,user,1,Ops\nA,3,user,1,Ops\n",  # duplicate
    ]
    for i, pop in enumerate(bad):
        sub = tmp_path / f"c{i}"
        sub.mkdir()
        res, _ = _run(sub, pop)
        assert res.returncode == 2, (pop, res.stderr)
        assert "error:" in res.stderr


def test_deterministic_outputs(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    _run(a, POP)
    _run(b, POP)
    for name in ("curriculum.csv", "training-load.csv", "adoption-plan.md", "adoption.json"):
        assert (a / "out" / name).read_bytes() == (b / "out" / name).read_bytes(), name


def test_verify_passes_and_detects_tampering(tmp_path):
    res, plan = _run(tmp_path, POP)
    out = tmp_path / "out"
    assert run_script(SCRIPT, "--verify", str(out / "curriculum.csv")).returncode == 0
    plan["totals"]["training_hours"] = 999
    (out / "adoption.json").write_text(json.dumps(plan), encoding="utf-8")
    bad = run_script(SCRIPT, "--verify", str(out / "adoption.json"))
    assert bad.returncode == 1 and "total training hours" in bad.stderr
