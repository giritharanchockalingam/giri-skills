#!/usr/bin/env python3
"""Validate a LangGraph graph spec and emit a StateGraph scaffold + Mermaid diagram.

Applies the graph rules of the upstream `langgraph-fundamentals` skill
(langchain-ai/langchain-skills, pinned in vendor/pins.json) as deterministic checks:

  errors (exit 1, no graph.py written)
    - spec shape: name, state[], nodes[], entry present; node names are unique Python
      identifiers and not START/END; kind in llm|tool|router|function
    - state field types known; reducers in add|add_messages and compatible with the type
    - dangling edges (unknown from/to); edges into START (START is entry-only)
    - every node reachable from the entry
    - END reachable from every node
    - every cycle (strongly connected component) has a conditional edge leaving it
    - router nodes have >= 2 conditional routes; one conditional-edge block per node
    - reads/writes reference declared state fields
  warnings (reported, exit 0)
    - a node with both static and conditional out-edges (both execute)
    - a list field written by >= 2 nodes without a reducer (last write wins)
    - a declared state field no node reads or writes

Spec (JSON):
  {"name": "...", "state": [{"name", "type", "reducer"?}],
   "nodes": [{"name", "kind", "description", "reads"?: [], "writes"?: []}],
   "edges": [{"from", "to"}], "conditional_edges": [{"from", "routes": {label: to}}],
   "entry": "<node>", "finish": ["<node>", ...]}
  `to` may be "END"; `finish` nodes get an edge to END.

The scaffold is generated as text and verified with compile()/ast.parse. It is NOT
executed and langgraph is NOT imported here.

Brownfield (--current-spec): pass the spec of the graph running today. The run diffs it against the new
spec — nodes, edges/routes and state fields added, removed or changed — and flags state changes that break
resuming threads already persisted by a checkpointer (a field removed, or its type or reducer changed).
The diff lands in validation.json ("change_vs_current") and graph.md ("Changes vs current graph").

Usage:
  python3 -I build_graph.py --spec graph-spec.json [--current-spec live-spec.json] --out-dir OUT
Writes OUT/validation.json and OUT/graph.md always; OUT/graph.py only when valid.
Exit: 0 valid · 1 validation errors · 2 spec missing or not JSON. Stdlib only.
"""
from __future__ import annotations

import argparse
import ast
import json
import keyword
import re
import sys
from pathlib import Path

KINDS = ("llm", "tool", "router", "function")
TYPES = {"str": "str", "int": "int", "float": "float", "bool": "bool", "list": "list",
         "dict": "dict", "any": "Any", "messages": "list"}
REDUCERS = {"add": ("list", "int", "float", "str", "messages"), "add_messages": ("list", "messages")}
RESERVED = {"START", "END", "__start__", "__end__"}
END = "END"
# identifiers the generated module defines or imports; a node with one of these names would shadow it
SCAFFOLD_NAMES = {"State", "build_graph", "StateGraph", "TypedDict", "Annotated", "Any", "Literal",
                  "operator", "add_messages", "annotations"}
SHAPES = {"llm": ("[", "]"), "tool": ("[[", "]]"), "router": ("{", "}"), "function": ("(", ")")}


# ------------------------------------------------------------------ helpers

def _ident(name: str) -> bool:
    return isinstance(name, str) and name.isidentifier() and not keyword.iskeyword(name)


def _as_list(v) -> list:
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]


def load_spec(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"error: spec not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"error: spec is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, dict):
        print("error: spec must be a JSON object", file=sys.stderr)
        sys.exit(2)
    return data


def out_edges(spec: dict) -> dict[str, list[tuple[str, str, str]]]:
    """node -> [(target, kind 'static'|'conditional', label)] including entry/finish edges."""
    g: dict[str, list[tuple[str, str, str]]] = {n["name"]: [] for n in spec["nodes"]}
    for e in spec["edges"]:
        g.setdefault(e["from"], []).append((e["to"], "static", ""))
    for f in spec["finish"]:
        g.setdefault(f, []).append((END, "static", ""))
    for c in spec["conditional_edges"]:
        for label, to in (c.get("routes") or {}).items():
            g.setdefault(c["from"], []).append((to, "conditional", str(label)))
    return g


def sccs(nodes: list[str], adj: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan's strongly connected components (iterative)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []
    counter = [0]
    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = counter[0]
                counter[0] += 1
                stack.append(v)
                on.add(v)
            succ = adj.get(v, [])
            recurse = False
            for j in range(i, len(succ)):
                w = succ[j]
                if w not in index:
                    work.append((v, j + 1))
                    work.append((w, 0))
                    recurse = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if recurse:
                continue
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                out.append(sorted(comp))
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[v])
    return out


# ------------------------------------------------------------------ validation

def normalise(spec: dict, errors: list[str]) -> dict:
    """Fill defaults and type-check the top-level shape (errors appended, never raised)."""
    s = {"name": str(spec.get("name") or "").strip(),
         "state": spec.get("state") or [], "nodes": spec.get("nodes") or [],
         "edges": spec.get("edges") or [], "conditional_edges": spec.get("conditional_edges") or [],
         "entry": str(spec.get("entry") or "").strip(), "finish": [str(x) for x in _as_list(spec.get("finish"))]}
    if not s["name"]:
        errors.append("spec.name is missing")
    for key in ("state", "nodes", "edges", "conditional_edges"):
        if not isinstance(s[key], list) or not all(isinstance(x, dict) for x in s[key]):
            errors.append(f"spec.{key} must be a list of objects")
            s[key] = []
    if not s["nodes"]:
        errors.append("spec.nodes is empty")
    if not s["entry"]:
        errors.append("spec.entry is missing")
    for e in s["edges"]:
        e["from"], e["to"] = str(e.get("from") or ""), str(e.get("to") or "")
    for c in s["conditional_edges"]:
        c["from"] = str(c.get("from") or "")
        if not isinstance(c.get("routes"), dict):
            errors.append(f"conditional edge from '{c['from']}': routes must be an object {{label: target}}")
            c["routes"] = {}
        c["routes"] = {str(k): str(v) for k, v in c["routes"].items()}
    for n in s["nodes"]:
        n["name"] = str(n.get("name") or "")
        n["kind"] = str(n.get("kind") or "")
        n["description"] = str(n.get("description") or "")
        n["reads"] = [str(x) for x in _as_list(n.get("reads"))]
        n["writes"] = [str(x) for x in _as_list(n.get("writes"))]
    return s


def validate(spec: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    s = normalise(spec, errors)

    # state
    fields: dict[str, dict] = {}
    for f in s["state"]:
        name, typ, red = str(f.get("name") or ""), str(f.get("type") or "").lower(), str(f.get("reducer") or "")
        if not _ident(name):
            errors.append(f"state field '{name}' is not a valid Python identifier")
            continue
        if name in fields:
            errors.append(f"state field '{name}' declared twice")
        if typ not in TYPES:
            errors.append(f"state field '{name}': type '{typ}' not in {sorted(TYPES)}")
        if red and red not in REDUCERS:
            errors.append(f"state field '{name}': reducer '{red}' not in {sorted(REDUCERS)}")
        elif red and typ in TYPES and typ not in REDUCERS[red]:
            errors.append(f"state field '{name}': reducer '{red}' does not apply to type '{typ}'")
        fields[name] = {"name": name, "type": typ, "reducer": red}
    if not fields:
        errors.append("spec.state is empty: a StateGraph needs at least one state field")

    # nodes
    names: list[str] = []
    for n in s["nodes"]:
        nm = n["name"]
        if nm in RESERVED:
            errors.append(f"node '{nm}' uses a reserved name (START/END)")
        elif not _ident(nm):
            errors.append(f"node '{nm}' is not a valid Python identifier")
        if nm in names:
            errors.append(f"node '{nm}' declared twice")
        names.append(nm)
        if n["kind"] not in KINDS:
            errors.append(f"node '{nm}': kind '{n['kind']}' not in {list(KINDS)}")
        if not n["description"]:
            warnings.append(f"node '{nm}' has no description")
        for ref in n["reads"] + n["writes"]:
            if ref not in fields:
                errors.append(f"node '{nm}' references undeclared state field '{ref}'")
    known = set(names)
    for nm in names:
        if nm in SCAFFOLD_NAMES:
            errors.append(f"node '{nm}' collides with a scaffold name {sorted(SCAFFOLD_NAMES)}")
    for c in s["conditional_edges"]:
        if f"route_{c['from']}" in known:
            errors.append(f"node 'route_{c['from']}' collides with the generated router function for '{c['from']}'")

    # edges
    for e in s["edges"]:
        if e["from"] in ("START", "__start__"):
            errors.append(f"edge START -> '{e['to']}': declare the entry with spec.entry instead")
        elif e["from"] not in known:
            errors.append(f"dangling edge: from '{e['from']}' is not a node")
        if e["to"] in ("START", "__start__"):
            errors.append(f"edge '{e['from']}' -> START: START is entry-only; route loops through a named node")
        elif e["to"] not in known and e["to"] != END:
            errors.append(f"dangling edge: '{e['from']}' -> '{e['to']}' (target is not a node or END)")
    seen_cond: set[str] = set()
    for c in s["conditional_edges"]:
        src = c["from"]
        if src not in known:
            errors.append(f"dangling conditional edge: from '{src}' is not a node")
        if src in seen_cond:
            errors.append(f"node '{src}' has more than one conditional_edges block; merge the routes")
        seen_cond.add(src)
        for label, to in c["routes"].items():
            if to in ("START", "__start__"):
                errors.append(f"route '{src}' -[{label}]-> START: START is entry-only")
            elif to not in known and to != END:
                errors.append(f"dangling route: '{src}' -[{label}]-> '{to}' (target is not a node or END)")
    for f in s["finish"]:
        if f not in known:
            errors.append(f"finish node '{f}' is not a node")
    if s["entry"] and s["entry"] not in known:
        errors.append(f"entry '{s['entry']}' is not a node")

    # routers
    route_count = {c["from"]: len(c["routes"]) for c in s["conditional_edges"]}
    for n in s["nodes"]:
        if n["kind"] == "router" and route_count.get(n["name"], 0) < 2:
            errors.append(f"router node '{n['name']}' has {route_count.get(n['name'], 0)} conditional route(s); needs >= 2")
    static_from = {e["from"] for e in s["edges"]} | set(s["finish"])
    for src in sorted(seen_cond & static_from):
        warnings.append(f"node '{src}' has static AND conditional out-edges: both execute on every run")

    # reducers: list fields written by several nodes
    writers: dict[str, list[str]] = {}
    for n in s["nodes"]:
        for w in n["writes"]:
            writers.setdefault(w, []).append(n["name"])
    for fname, f in fields.items():
        if f["type"] in ("list", "messages") and not f["reducer"] and len(writers.get(fname, [])) >= 2:
            warnings.append(f"list field '{fname}' is written by {writers[fname]} without a reducer: last write wins")
    used = {r for n in s["nodes"] for r in n["reads"] + n["writes"]}
    for fname in fields:
        if fname not in used:
            warnings.append(f"state field '{fname}' is not read or written by any node")

    # graph analysis (only over known endpoints)
    g = out_edges(s)
    adj = {k: [t for t, _, _ in v if t in known] for k, v in g.items() if k in known}
    reach: set[str] = set()
    if s["entry"] in known:
        todo = [s["entry"]]
        while todo:
            v = todo.pop()
            if v in reach:
                continue
            reach.add(v)
            todo += adj.get(v, [])
    unreachable = [n for n in names if n not in reach]
    for n in unreachable:
        errors.append(f"node '{n}' is not reachable from entry '{s['entry']}'")
    reaches_end: set[str] = set()
    rev: dict[str, list[str]] = {}
    for k, v in g.items():
        for t, _, _ in v:
            rev.setdefault(t, []).append(k)
    todo = list(rev.get(END, []))
    while todo:
        v = todo.pop()
        if v in reaches_end or v not in known:
            continue
        reaches_end.add(v)
        todo += rev.get(v, [])
    no_end = [n for n in names if n not in reaches_end]
    for n in no_end:
        errors.append(f"END is not reachable from node '{n}'")
    cycles = []
    for comp in sccs([n for n in names if n in known], adj):
        is_cycle = len(comp) > 1 or comp[0] in adj.get(comp[0], [])
        if not is_cycle:
            continue
        cset = set(comp)
        exits = [f"{v} -[{lbl}]-> {t}" for v in comp for t, kind, lbl in g.get(v, [])
                 if kind == "conditional" and t not in cset]
        cycles.append({"nodes": comp, "conditional_exits": exits})
        if not exits:
            errors.append(f"cycle {comp} has no conditional exit: it can loop forever")

    return {"spec": s, "fields": fields, "errors": errors, "warnings": warnings,
            "unreachable": unreachable, "no_path_to_end": no_end, "cycles": cycles,
            "stats": {"nodes": len(names), "state_fields": len(fields), "static_edges": len(s["edges"]) + len(s["finish"]) + (1 if s["entry"] else 0),
                      "conditional_routes": sum(route_count.values()), "cycles": len(cycles)}}


# ------------------------------------------------------------------ generation

def _target(t: str) -> str:
    return "END" if t == END else repr(t)


def gen_python(v: dict, spec_name: str) -> str:
    s, fields = v["spec"], v["fields"]
    reducers = {f["reducer"] for f in fields.values()}
    lines = [
        f'"""{s["name"]} — LangGraph scaffold generated by langgraph-runner from {spec_name}.',
        "",
        "Generated as text and syntax-checked (compile/ast.parse) by langgraph-runner; it was NOT",
        "executed. Implement every NotImplementedError stub, then run it in an environment with",
        "langgraph installed. Graph rules applied: see langgraph-fundamentals (vendor/pins.json).",
        '"""',
        "from __future__ import annotations",
        "",
    ]
    if "add" in reducers:
        lines.append("import operator")
    lines += ["from typing import Annotated, Any, Literal", "",
              "from typing_extensions import TypedDict", "",
              "from langgraph.graph import END, START, StateGraph"]
    if "add_messages" in reducers:
        lines.append("from langgraph.graph.message import add_messages")
    lines += ["", "", "class State(TypedDict):",
              f'    """Shared state for {s["name"]}. Nodes return partial updates; never mutate state."""', ""]
    for f in fields.values():
        py = TYPES.get(f["type"], "Any")
        if f["reducer"] == "add":
            lines.append(f"    {f['name']}: Annotated[{py}, operator.add]  # reducer: accumulates")
        elif f["reducer"] == "add_messages":
            lines.append(f"    {f['name']}: Annotated[list, add_messages]  # reducer: message history")
        else:
            lines.append(f"    {f['name']}: {py}  # no reducer: last write wins")
    lines += ["", ""]
    routes = {c["from"]: c["routes"] for c in s["conditional_edges"]}
    for n in s["nodes"]:
        desc = n["description"].replace('"""', "'''") or "(no description in spec)"
        lines += [f"def {n['name']}(state: State) -> dict:",
                  f'    """[{n["kind"]}] {desc}',
                  "",
                  f"    Reads: {', '.join(n['reads']) or '-'}. Writes: {', '.join(n['writes']) or '-'}.",
                  "    Return a dict with only the fields this node updates.",
                  '    """',
                  f"    raise NotImplementedError({n['name']!r})", "", ""]
    for src, rt in routes.items():
        labels = ", ".join(repr(k) for k in rt)
        lines += [f"def route_{src}(state: State) -> Literal[{labels}]:",
                  f'    """Choose the next step after {src}; return one of the route labels."""',
                  f"    raise NotImplementedError('route_{src}')", "", ""]
    lines += ["def build_graph(checkpointer: Any = None):",
              '    """Wire the graph and compile it (compile() is required before invoke/stream)."""',
              "    builder = StateGraph(State)"]
    for n in s["nodes"]:
        lines.append(f"    builder.add_node({n['name']!r}, {n['name']})")
    lines.append(f"    builder.add_edge(START, {s['entry']!r})")
    for e in s["edges"]:
        lines.append(f"    builder.add_edge({e['from']!r}, {_target(e['to'])})")
    for f in s["finish"]:
        lines.append(f"    builder.add_edge({f!r}, END)")
    for src, rt in routes.items():
        pm = ", ".join(f"{k!r}: {_target(t)}" for k, t in rt.items())
        lines.append(f"    builder.add_conditional_edges({src!r}, route_{src}, {{{pm}}})")
    lines += ["    return builder.compile(checkpointer=checkpointer)", "", "",
              'if __name__ == "__main__":',
              "    print(build_graph().get_graph().draw_mermaid())", ""]
    return "\n".join(lines)


def syntax_check(src: str, filename: str) -> tuple[bool, str]:
    try:
        compile(src, filename, "exec")
        ast.parse(src)
        return True, "compile() and ast.parse() succeeded"
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"


def _mlabel(text: str) -> str:
    return re.sub(r"[^\w .:-]", "", text).strip() or "route"


def gen_mermaid(v: dict) -> str:
    s = v["spec"]
    kinds = {n["name"]: n["kind"] for n in s["nodes"]}
    out = ["flowchart TD", "    __start__([START])", "    __end__([END])"]
    for n in s["nodes"]:
        o, c = SHAPES.get(n["kind"], ("[", "]"))
        out.append(f"    {n['name']}{o}{n['name']}{c}")

    def ref(t: str) -> str:
        return "__end__" if t == END else (t if t in kinds else "__end__")
    if s["entry"]:
        out.append(f"    __start__ --> {s['entry']}")
    for e in s["edges"]:
        if e["from"] in kinds:
            out.append(f"    {e['from']} --> {ref(e['to'])}")
    for f in s["finish"]:
        if f in kinds:
            out.append(f"    {f} --> __end__")
    for c in s["conditional_edges"]:
        if c["from"] in kinds:
            for label, t in c["routes"].items():
                out.append(f"    {c['from']} -->|{_mlabel(label)}| {ref(t)}")
    return "\n".join(out)


def _edge_set(v: dict) -> set[tuple[str, str, str]]:
    return {(src, t, lbl) for src, outs in out_edges(v["spec"]).items() for t, _kind, lbl in outs}


def diff_specs(cur: dict, new: dict, current_name: str) -> dict:
    """Changes from the graph running today (cur) to the new spec (new); both are validate() results."""
    cn = {n["name"]: n for n in cur["spec"]["nodes"]}
    nn = {n["name"]: n for n in new["spec"]["nodes"]}
    node_changes = [{"node": k, "change": "added", "kind": nn[k]["kind"]} for k in nn if k not in cn]
    node_changes += [{"node": k, "change": "removed", "kind": cn[k]["kind"]} for k in cn if k not in nn]
    node_changes += [{"node": k, "change": f"kind {cn[k]['kind']} -> {nn[k]['kind']}", "kind": nn[k]["kind"]}
                     for k in nn if k in cn and cn[k]["kind"] != nn[k]["kind"]]
    ce, ne = _edge_set(cur), _edge_set(new)

    def edge(e, change):
        return {"from": e[0], "to": e[1], "route": e[2], "change": change}
    edge_changes = [edge(e, "added") for e in sorted(ne - ce)] + [edge(e, "removed") for e in sorted(ce - ne)]
    cf, nf = cur["fields"], new["fields"]
    state_changes, breaking = [], []
    for k in nf:
        if k not in cf:
            state_changes.append({"field": k, "change": "added", "breaks_resume": False})
    for k in cf:
        if k not in nf:
            state_changes.append({"field": k, "change": "removed", "breaks_resume": True})
        elif (cf[k]["type"], cf[k]["reducer"]) != (nf[k]["type"], nf[k]["reducer"]):
            state_changes.append({"field": k, "breaks_resume": True,
                                  "change": f"{cf[k]['type']}/{cf[k]['reducer'] or 'no reducer'} -> "
                                            f"{nf[k]['type']}/{nf[k]['reducer'] or 'no reducer'}"})
    breaking = [c["field"] for c in state_changes if c["breaks_resume"]]
    entry = None if cur["spec"]["entry"] == new["spec"]["entry"] else \
        {"current": cur["spec"]["entry"], "proposed": new["spec"]["entry"]}
    return {"current_spec": current_name, "current_valid": not cur["errors"], "entry_change": entry,
            "node_changes": node_changes, "edge_changes": edge_changes, "state_changes": state_changes,
            "resume_breaking_fields": breaking,
            "total_changes": len(node_changes) + len(edge_changes) + len(state_changes) + (1 if entry else 0)}


def gen_change_markdown(d: dict) -> list[str]:
    lines = ["## Changes vs current graph", "",
             f"Compared with the graph running today (`{d['current_spec']}`"
             f"{'' if d['current_valid'] else ', which itself fails validation'}): {d['total_changes']} change(s) — "
             f"{len(d['node_changes'])} node, {len(d['edge_changes'])} edge, {len(d['state_changes'])} state.", ""]
    if d["entry_change"]:
        lines += [f"Entry moves from `{d['entry_change']['current']}` to `{d['entry_change']['proposed']}`.", ""]
    if d["node_changes"]:
        lines += ["| Node | Change | Kind |", "|---|---|---|"]
        lines += [f"| {c['node']} | {c['change']} | {c['kind']} |" for c in d["node_changes"]] + [""]
    if d["edge_changes"]:
        lines += ["| From | To | Route | Change |", "|---|---|---|---|"]
        lines += [f"| {c['from']} | {c['to']} | {c['route'] or '-'} | {c['change']} |" for c in d["edge_changes"]] + [""]
    if d["state_changes"]:
        lines += ["| State field | Change | Breaks resume of persisted threads |", "|---|---|---|"]
        lines += [f"| {c['field']} | {c['change']} | {'yes' if c['breaks_resume'] else 'no'} |"
                  for c in d["state_changes"]] + [""]
    if d["resume_breaking_fields"]:
        lines += [f"Threads checkpointed under the current graph cannot resume safely ({', '.join(d['resume_breaking_fields'])}): "
                  "drain in-flight threads or migrate their checkpoints before deploying.", ""]
    if not d["total_changes"]:
        lines += ["No structural change.", ""]
    return lines


def gen_markdown(v: dict, scaffold: dict, spec_name: str, change: dict | None = None) -> str:
    s = v["spec"]
    ok = not v["errors"]
    lines = [f"# LangGraph scaffold — {s['name'] or '(unnamed)'}", "",
             f"Verdict: **{'VALID' if ok else 'INVALID'}** — {len(v['errors'])} error(s), {len(v['warnings'])} warning(s). "
             f"Spec: `{spec_name}`. Wraps langgraph-fundamentals from langchain-ai/langchain-skills (pinned in vendor/pins.json).",
             "", "## Diagram", "", "```mermaid", gen_mermaid(v), "```", "",
             "Shapes: `[llm]` · `[[tool]]` · `{router}` · `(function)`; labelled arrows are conditional routes.", "",
             "## Validation", "",
             "| Check | Result |", "|---|---|",
             f"| Nodes reachable from entry `{s['entry']}` | {'all' if not v['unreachable'] else 'unreachable: ' + ', '.join(v['unreachable'])} |",
             f"| END reachable from every node | {'yes' if not v['no_path_to_end'] else 'no path from: ' + ', '.join(v['no_path_to_end'])} |",
             f"| Cycles with a conditional exit | {sum(1 for c in v['cycles'] if c['conditional_exits'])} of {len(v['cycles'])} |",
             f"| Scaffold | {scaffold['status']} |", ""]
    if v["errors"]:
        lines += ["Errors (fix the spec and re-run):", ""] + [f"- {e}" for e in v["errors"]] + [""]
    if v["warnings"]:
        lines += ["Warnings:", ""] + [f"- {w}" for w in v["warnings"]] + [""]
    if not v["errors"] and not v["warnings"]:
        lines += ["No errors or warnings.", ""]
    lines += ["## Nodes", "", "| Node | Kind | Description | Reads | Writes | Out-edges |", "|---|---|---|---|---|---|"]
    g = out_edges(s)
    for n in s["nodes"]:
        outs = ", ".join((f"{t} [{lbl}]" if kind == "conditional" else t) for t, kind, lbl in g.get(n["name"], [])) or "-"
        lines.append(f"| {n['name']} | {n['kind']} | {n['description'] or '-'} | {', '.join(n['reads']) or '-'} | "
                     f"{', '.join(n['writes']) or '-'} | {outs} |")
    lines += ["", "State:", "", "| Field | Type | Reducer |", "|---|---|---|"]
    for f in v["fields"].values():
        lines.append(f"| {f['name']} | {f['type']} | {f['reducer'] or 'none (last write wins)'} |")
    lines.append("")
    if change:
        lines += gen_change_markdown(change)
    lines += ["## How to run", ""]
    if ok:
        lines += ["1. `graph.py` was generated and syntax-checked, not executed. Install `langgraph` in your project environment.",
                  "2. Implement each node stub (return partial state updates) and each `route_<node>` function.",
                  "3. Smoke-test: `python graph.py` prints the compiled graph as Mermaid; compare with the diagram above.",
                  "4. Invoke: `build_graph().invoke({...initial state...})`; pass a checkpointer and a `thread_id` config if you add interrupts (see langgraph-hitl-runner).",
                  "5. Re-run this skill after every spec change; the validation gate must stay green."]
    else:
        lines += ["No scaffold was written because the spec failed validation. Fix the errors above and re-run."]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a LangGraph spec; emit graph.py, graph.md, validation.json")
    ap.add_argument("--spec", required=True, help="graph spec JSON (layout: assets/graph-spec.example.json)")
    ap.add_argument("--current-spec", help="spec of the graph running today (brownfield diff)")
    ap.add_argument("--out-dir", required=True, help="directory for graph.py, graph.md, validation.json")
    a = ap.parse_args(argv)
    spec_path = Path(a.spec)
    raw = load_spec(spec_path)
    v = validate(raw)
    change = None
    if a.current_spec:
        cur_path = Path(a.current_spec)
        change = diff_specs(validate(load_spec(cur_path)), v, cur_path.name)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    scaffold = {"generated": False, "syntax_checked": False, "executed": False,
                "status": "not generated (validation failed)"}
    if not v["errors"]:
        src = gen_python(v, spec_path.name)
        ok, detail = syntax_check(src, "graph.py")
        scaffold = {"generated": True, "syntax_checked": ok, "executed": False, "detail": detail,
                    "status": f"generated and syntax-checked ({detail}); not executed"}
        if ok:
            (out / "graph.py").write_text(src, encoding="utf-8")
        else:
            v["errors"].append(f"generated scaffold failed the syntax check: {detail}")
    (out / "graph.md").write_text(gen_markdown(v, scaffold, spec_path.name, change), encoding="utf-8")
    report = {"spec": v["spec"]["name"], "source": spec_path.name, "valid": not v["errors"],
              "errors": v["errors"], "warnings": v["warnings"], "stats": v["stats"],
              "unreachable": v["unreachable"], "no_path_to_end": v["no_path_to_end"],
              "cycles": v["cycles"], "scaffold": scaffold,
              **({"change_vs_current": change} if change else {}),
              "upstream": "langgraph-fundamentals (langchain-ai/langchain-skills, vendor/pins.json)"}
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['spec']}: {'VALID' if report['valid'] else 'INVALID'} — "
          f"{len(v['errors'])} error(s), {len(v['warnings'])} warning(s); wrote {out}")
    for e in v["errors"]:
        print(f"  error: {e}", file=sys.stderr)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
