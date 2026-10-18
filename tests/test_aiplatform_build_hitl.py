"""Tests for ai-platform/langgraph-hitl-runner/scripts/build_hitl.py."""
from __future__ import annotations

import ast
import json
import re

from conftest import REPO_ROOT, run_script

SKILL = "skills/ai-platform/langgraph-hitl-runner"
SCRIPT = f"{SKILL}/scripts/build_hitl.py"
CHECK = f"{SKILL}/scripts/check_syntax.py"


def _gate(**over):
    g = {"before_node": "pay", "reason": "moves money", "approver_role": "Finance lead",
         "timeout_minutes": 60, "on_timeout": "reject", "editable_fields": ["amount"],
         "high_impact": True, "irreversible": True}
    g.update(over)
    return g


def _run(tmp_path, spec):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--spec", str(p), "--out-dir", str(out))
    v = json.loads((out / "validation.json").read_text(encoding="utf-8"))
    return r, v, out


def _spec(*gates, cp="sqlite", **over):
    s = {"graph": "g", "checkpointer": cp, "interrupts": list(gates) or [_gate()]}
    s.update(over)
    return s


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_valid_spec_generates_checked_scaffold(tmp_path):
    r, v, out = _run(tmp_path, _spec())
    assert r.returncode == 0, r.stderr
    assert v["valid"] and v["errors"] == [] and v["warnings"] == []
    src = (out / "hitl.py").read_text(encoding="utf-8")
    defs = {n.name for n in ast.parse(src).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    assert {"State", "approve_pay", "pay", "make_checkpointer", "build_graph", "start", "resume", "resume_on_timeout"} <= defs
    assert "SqliteSaver" in src and "Command(resume=decision)" in src
    # interrupt() is the first statement after reading the policy in the gate
    gate = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "approve_pay")
    assert "interrupt" in ast.unparse(gate.body[2])
    assert run_script(CHECK, str(out / "hitl.py"), "--require", "resume").returncode == 0
    assert v["scaffold"] == {"generated": True, "syntax_checked": True, "executed": False,
                             "detail": "compile() and ast.parse() succeeded",
                             "status": "generated and syntax-checked (compile() and ast.parse() succeeded); not executed"}


def test_approval_matrix_row(tmp_path):
    _, _, out = _run(tmp_path, _spec())
    md = (out / "hitl.md").read_text(encoding="utf-8")
    for h in ("## Approval matrix", "## Validation", "## Resume flow", "## Risks"):
        assert h in md
    assert "| pay | moves money | Finance lead | 60 | reject | - | amount | yes | yes |" in md


def test_missing_checkpointer_is_error(tmp_path):
    r, v, out = _run(tmp_path, _spec(cp=""))
    assert r.returncode == 1
    assert any("checkpointer is required" in e for e in v["errors"])
    assert not (out / "hitl.py").exists()


def test_irreversible_auto_approve_forbidden(tmp_path):
    r, v, _ = _run(tmp_path, _spec(_gate(on_timeout="auto-approve")))
    assert r.returncode == 1
    assert any("auto-approve on timeout is forbidden" in e for e in v["errors"])


def test_reversible_auto_approve_only_warns(tmp_path):
    r, v, _ = _run(tmp_path, _spec(_gate(on_timeout="auto-approve", irreversible=False)))
    assert r.returncode == 0
    assert any("silence equals consent" in w for w in v["warnings"])


def test_high_impact_needs_timeout(tmp_path):
    r, v, _ = _run(tmp_path, _spec(_gate(timeout_minutes=None, irreversible=False)))
    assert r.returncode == 1
    assert any("needs a timeout policy" in e for e in v["errors"])


def test_low_impact_without_timeout_warns_only(tmp_path):
    r, v, _ = _run(tmp_path, _spec(_gate(timeout_minutes=None, irreversible=False, high_impact=False)))
    assert r.returncode == 0
    assert any("policy never fires" in w for w in v["warnings"])


def test_missing_role_reason_and_bad_policy(tmp_path):
    r, v, _ = _run(tmp_path, _spec(_gate(approver_role="", reason="", on_timeout="ignore")))
    errs = "\n".join(v["errors"])
    assert r.returncode == 1
    assert "approver_role is missing" in errs and "reason is missing" in errs and "on_timeout 'ignore'" in errs


def test_editable_field_must_be_declared(tmp_path):
    r, v, _ = _run(tmp_path, _spec(state_fields=["total"]))
    assert r.returncode == 1
    assert any("editable field 'amount' is not in state_fields" in e for e in v["errors"])


def test_escalation_gate_and_tbd_owner(tmp_path):
    r, v, out = _run(tmp_path, _spec(_gate(on_timeout="escalate"), cp="memory"))
    assert r.returncode == 0
    src = (out / "hitl.py").read_text(encoding="utf-8")
    assert "def escalate_pay" in src and "InMemorySaver" in src
    md = (out / "hitl.md").read_text(encoding="utf-8")
    assert "[TO BE BASELINED — owner: Process owner]" in md
    assert "In-memory checkpointer loses every pending approval" in md
    assert len(v["warnings"]) == 2  # memory checkpointer + escalate without escalate_to


def test_gates_wired_in_order(tmp_path):
    _, _, out = _run(tmp_path, _spec(_gate(), _gate(before_node="notify", irreversible=False, high_impact=False), cp="postgres"))
    src = (out / "hitl.py").read_text(encoding="utf-8")
    assert "builder.add_edge(START, 'approve_pay')" in src
    assert "builder.add_edge('pay', 'approve_notify')" in src
    assert "builder.add_edge('notify', END)" in src
    assert "PostgresSaver" in src and "LANGGRAPH_PG_DSN" in src


def test_duplicate_gate_and_bad_node_name(tmp_path):
    _, v, _ = _run(tmp_path, _spec(_gate(), _gate(), _gate(before_node="2bad")))
    errs = "\n".join(v["errors"])
    assert "declared twice" in errs and "must be a Python identifier" in errs


def test_missing_spec_exits_2(tmp_path):
    assert run_script(SCRIPT, "--spec", str(tmp_path / "x.json"), "--out-dir", str(tmp_path / "o")).returncode == 2


def test_fixtures_are_labelled_fictional():
    for f in (REPO_ROOT / SKILL / "evals" / "fixtures").glob("*.json"):
        assert "fictional" in json.loads(f.read_text(encoding="utf-8"))["_note"]


def test_scripts_have_no_network_or_subprocess():
    for f in (REPO_ROOT / SKILL / "scripts").glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(socket|urllib|requests|http|subprocess)\b", src, re.M), f
