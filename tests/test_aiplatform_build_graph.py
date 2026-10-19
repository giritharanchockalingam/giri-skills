"""Tests for ai-platform/langgraph-runner/scripts/build_graph.py (and check_syntax.py)."""
from __future__ import annotations

import ast
import json
import re

from conftest import REPO_ROOT, run_script

SKILL = "skills/ai-platform/langgraph-runner"
SCRIPT = f"{SKILL}/scripts/build_graph.py"
CHECK = f"{SKILL}/scripts/check_syntax.py"


def _spec(**over):
    spec = {
        "name": "g",
        "state": [{"name": "msgs", "type": "list", "reducer": "add"}, {"name": "n", "type": "int"}],
        "nodes": [
            {"name": "a", "kind": "llm", "description": "first", "reads": ["msgs"], "writes": ["msgs"]},
            {"name": "r", "kind": "router", "description": "route", "reads": ["n"]},
            {"name": "b", "kind": "tool", "description": "work", "writes": ["msgs", "n"]},
        ],
        "edges": [{"from": "a", "to": "r"}, {"from": "b", "to": "a"}],
        "conditional_edges": [{"from": "r", "routes": {"again": "b", "done": "END"}}],
        "entry": "a",
        "finish": [],
    }
    spec.update(over)
    return spec


def _run(tmp_path, spec):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--spec", str(p), "--out-dir", str(out))
    v = json.loads((out / "validation.json").read_text(encoding="utf-8")) if (out / "validation.json").exists() else None
    return r, v, out


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_valid_loop_with_conditional_exit(tmp_path):
    r, v, out = _run(tmp_path, _spec())
    assert r.returncode == 0, r.stderr
    assert v["valid"] is True and v["errors"] == []
    # one cycle {a, r, b} with exactly the conditional exit r -[done]-> END
    assert v["cycles"] == [{"nodes": ["a", "b", "r"], "conditional_exits": ["r -[done]-> END"]}]
    assert v["stats"] == {"nodes": 3, "state_fields": 2, "static_edges": 3, "conditional_routes": 2, "cycles": 1}
    assert v["scaffold"]["syntax_checked"] is True and v["scaffold"]["executed"] is False


def test_scaffold_is_valid_python_with_wiring(tmp_path):
    _, _, out = _run(tmp_path, _spec())
    src = (out / "graph.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    defs = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    assert {"State", "a", "r", "b", "route_r", "build_graph"} <= defs
    assert "msgs: Annotated[list, operator.add]" in src
    assert "builder.add_edge(START, 'a')" in src
    assert "builder.add_conditional_edges('r', route_r, {'again': 'b', 'done': END})" in src
    assert "import langgraph" not in src.split('"""')[0]  # generated, not imported by us
    r = run_script(CHECK, str(out / "graph.py"), "--require", "build_graph", "--require", "State")
    assert r.returncode == 0, r.stdout


def test_markdown_sections_and_mermaid(tmp_path):
    _, _, out = _run(tmp_path, _spec())
    md = (out / "graph.md").read_text(encoding="utf-8")
    for h in ("## Diagram", "## Validation", "## Nodes", "## How to run"):
        assert h in md
    block = re.search(r"```mermaid\n(.*?)```", md, re.S).group(1)
    assert "__start__ --> a" in block and "r -->|done| __end__" in block
    assert "r{r}" in block and "b[[b]]" in block  # router and tool shapes
    assert "not executed" in md


def test_static_loop_without_conditional_exit_is_error(tmp_path):
    spec = _spec(conditional_edges=[], edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
                 nodes=[{"name": "a", "kind": "llm", "description": "x"}, {"name": "b", "kind": "tool", "description": "y"}],
                 finish=["b"])
    r, v, out = _run(tmp_path, spec)
    assert r.returncode == 1
    assert any("has no conditional exit" in e for e in v["errors"])
    assert not (out / "graph.py").exists()


def test_reachability_and_end_errors(tmp_path):
    spec = _spec()
    spec["nodes"].append({"name": "orphan", "kind": "function", "description": "unwired"})
    spec["nodes"].append({"name": "sink", "kind": "function", "description": "no exit"})
    spec["edges"].append({"from": "orphan", "to": "sink"})
    r, v, _ = _run(tmp_path, spec)
    assert r.returncode == 1
    assert v["unreachable"] == ["orphan", "sink"]
    assert v["no_path_to_end"] == ["orphan", "sink"]


def test_dangling_router_and_state_errors(tmp_path):
    spec = _spec(conditional_edges=[{"from": "r", "routes": {"only": "b"}}])
    spec["edges"].append({"from": "b", "to": "ghost"})
    spec["nodes"][0]["reads"] = ["missing_field"]
    r, v, _ = _run(tmp_path, spec)
    errs = "\n".join(v["errors"])
    assert r.returncode == 1
    assert "dangling edge: 'b' -> 'ghost'" in errs
    assert "router node 'r' has 1 conditional route(s)" in errs
    assert "undeclared state field 'missing_field'" in errs


def test_start_is_entry_only_and_reserved_names(tmp_path):
    spec = _spec()
    spec["edges"].append({"from": "b", "to": "START"})
    spec["nodes"].append({"name": "build_graph", "kind": "function", "description": "clash"})
    _, v, _ = _run(tmp_path, spec)
    errs = "\n".join(v["errors"])
    assert "START is entry-only" in errs
    assert "collides with a scaffold name" in errs


def test_reducer_and_mixed_edge_warnings(tmp_path):
    spec = _spec(state=[{"name": "msgs", "type": "list"}, {"name": "n", "type": "int"}])
    spec["edges"].append({"from": "r", "to": "b"})  # static + conditional from r
    r, v, _ = _run(tmp_path, spec)
    assert r.returncode == 0
    w = "\n".join(v["warnings"])
    assert "list field 'msgs' is written by ['a', 'b'] without a reducer" in w
    assert "node 'r' has static AND conditional out-edges" in w


def test_bad_reducer_type_is_error(tmp_path):
    spec = _spec(state=[{"name": "msgs", "type": "dict", "reducer": "add"}, {"name": "n", "type": "int"}])
    _, v, _ = _run(tmp_path, spec)
    assert any("reducer 'add' does not apply to type 'dict'" in e for e in v["errors"])


def test_missing_spec_file_exits_2(tmp_path):
    r = run_script(SCRIPT, "--spec", str(tmp_path / "nope.json"), "--out-dir", str(tmp_path / "o"))
    assert r.returncode == 2


def test_invalid_json_exits_2(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert run_script(SCRIPT, "--spec", str(p), "--out-dir", str(tmp_path / "o")).returncode == 2


def test_fixtures_are_labelled_fictional():
    for f in (REPO_ROOT / SKILL / "evals" / "fixtures").glob("*.json"):
        assert "fictional" in json.loads(f.read_text(encoding="utf-8"))["_note"]


def test_scripts_have_no_network_or_subprocess():
    for f in (REPO_ROOT / SKILL / "scripts").glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(socket|urllib|requests|http|subprocess)\b", src, re.M), f


# --- brownfield: diff against the graph running today (--current-spec) ---

def _run_vs(tmp_path, spec, current):
    p, c = tmp_path / "spec.json", tmp_path / "live.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    c.write_text(json.dumps(current), encoding="utf-8")
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--spec", str(p), "--current-spec", str(c), "--out-dir", str(out))
    return r, json.loads((out / "validation.json").read_text(encoding="utf-8")), out


def test_identical_spec_has_no_changes(tmp_path):
    r, v, out = _run_vs(tmp_path, _spec(), _spec())
    assert r.returncode == 0, r.stderr
    assert v["change_vs_current"]["total_changes"] == 0
    assert "No structural change." in (out / "graph.md").read_text(encoding="utf-8")


def test_node_edge_and_state_changes(tmp_path):
    live = _spec(state=[{"name": "msgs", "type": "list", "reducer": "add"}, {"name": "n", "type": "int"},
                        {"name": "old", "type": "str"}])
    new = _spec(nodes=_spec()["nodes"] + [{"name": "c", "kind": "function", "description": "new step"}],
                edges=[{"from": "a", "to": "r"}, {"from": "b", "to": "c"}, {"from": "c", "to": "a"}])
    r, v, out = _run_vs(tmp_path, new, live)
    assert r.returncode == 0, r.stderr
    d = v["change_vs_current"]
    assert d["node_changes"] == [{"node": "c", "change": "added", "kind": "function"}]
    assert {(e["from"], e["to"], e["change"]) for e in d["edge_changes"]} == {
        ("b", "c", "added"), ("c", "a", "added"), ("b", "a", "removed")}
    assert d["state_changes"] == [{"field": "old", "change": "removed", "breaks_resume": True}]
    assert d["resume_breaking_fields"] == ["old"]
    assert "cannot resume safely (old)" in (out / "graph.md").read_text(encoding="utf-8")


def test_reducer_change_breaks_resume(tmp_path):
    live = _spec(state=[{"name": "msgs", "type": "list"}, {"name": "n", "type": "int"}])
    _, v, _ = _run_vs(tmp_path, _spec(), live)
    assert v["change_vs_current"]["state_changes"] == [
        {"field": "msgs", "breaks_resume": True, "change": "list/no reducer -> list/add"}]


def test_invalid_current_spec_still_diffed_and_flagged(tmp_path):
    r, v, out = _run_vs(tmp_path, _spec(), _spec(entry=""))
    assert r.returncode == 0  # the new spec decides the gate
    d = v["change_vs_current"]
    assert d["current_valid"] is False and d["entry_change"] == {"current": "", "proposed": "a"}
    assert "which itself fails validation" in (out / "graph.md").read_text(encoding="utf-8")


def test_without_current_spec_no_change_section(tmp_path):
    _, v, out = _run(tmp_path, _spec())
    assert "change_vs_current" not in v
    assert "Changes vs current graph" not in (out / "graph.md").read_text(encoding="utf-8")
