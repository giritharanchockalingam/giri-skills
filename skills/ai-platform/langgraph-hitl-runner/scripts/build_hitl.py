#!/usr/bin/env python3
"""Validate a human-approval spec for a LangGraph graph; emit an interrupt/resume scaffold.

Applies the requirements of the upstream `langgraph-human-in-the-loop` skill
(langchain-ai/langchain-skills, pinned in vendor/pins.json) as deterministic checks.

Spec (JSON):
  {"graph": "<name>", "checkpointer": "memory|postgres|sqlite",
   "state_fields"?: ["amount", ...],
   "interrupts": [{"before_node", "reason", "approver_role", "timeout_minutes"?,
                   "on_timeout": "reject|escalate|auto-approve", "escalate_to"?,
                   "editable_fields": [], "high_impact"?: bool, "irreversible"?: bool}]}

Errors (exit 1; no hitl.py written):
  graph name missing; interrupts empty; checkpointer missing or not memory|postgres|sqlite
  (interrupts cannot pause without one); before_node not a unique Python identifier;
  reason or approver_role missing; on_timeout missing or invalid; timeout_minutes not a
  positive number; high-impact or irreversible gate without timeout_minutes; irreversible
  gate with on_timeout=auto-approve; editable field not an identifier or not in state_fields
  (when state_fields is given).
Warnings: memory checkpointer (dev only); escalate without escalate_to; on_timeout set but
  no timeout_minutes (policy never fires); auto-approve on any gate.

The scaffold is generated as text and verified with compile()/ast.parse. It is NOT executed
and langgraph is NOT imported here.

Usage: python3 -I build_hitl.py --spec approvals.json --out-dir OUT
Writes OUT/validation.json and OUT/hitl.md always; OUT/hitl.py only when valid.
Exit: 0 valid · 1 validation errors · 2 spec missing or not JSON. Stdlib only.
"""
from __future__ import annotations

import argparse
import ast
import json
import keyword
import sys
from pathlib import Path

CHECKPOINTERS = ("memory", "postgres", "sqlite")
ON_TIMEOUT = ("reject", "escalate", "auto-approve")
RESERVED = {"State", "build_graph", "make_checkpointer", "start", "resume", "resume_on_timeout",
            "pending_approvals", "interrupt", "Command", "END", "START", "StateGraph"}


def _ident(s) -> bool:
    return isinstance(s, str) and s.isidentifier() and not keyword.iskeyword(s)


def _truthy(v) -> bool:
    return v is True or str(v).strip().lower() in ("true", "yes", "1", "y")


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


# ------------------------------------------------------------------ validation

def validate(spec: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    graph = str(spec.get("graph") or "").strip()
    if not graph:
        errors.append("spec.graph (graph name) is missing")
    cp = str(spec.get("checkpointer") or "").strip().lower()
    raw = spec.get("interrupts")
    if not isinstance(raw, list) or not raw:
        errors.append("spec.interrupts is empty: nothing to gate")
        raw = []
    if not cp:
        errors.append("checkpointer is required: interrupts cannot pause and resume without saved state")
    elif cp not in CHECKPOINTERS:
        errors.append(f"checkpointer '{cp}' not in {list(CHECKPOINTERS)}")
    elif cp == "memory":
        warnings.append("checkpointer 'memory' keeps paused threads in process memory: lost on restart; use postgres or sqlite beyond development")
    state_fields = spec.get("state_fields")
    declared = {str(x) for x in state_fields} if isinstance(state_fields, list) else None

    gates: list[dict] = []
    seen: set[str] = set()
    for i, it in enumerate(raw):
        if not isinstance(it, dict):
            errors.append(f"interrupt #{i + 1} is not an object")
            continue
        node = str(it.get("before_node") or "").strip()
        tag = f"gate before '{node or f'#{i + 1}'}'"
        g = {"before_node": node, "reason": str(it.get("reason") or "").strip(),
             "approver_role": str(it.get("approver_role") or "").strip(),
             "timeout_minutes": it.get("timeout_minutes"),
             "on_timeout": str(it.get("on_timeout") or "").strip().lower(),
             "escalate_to": str(it.get("escalate_to") or "").strip(),
             "editable_fields": it.get("editable_fields") or [],
             "high_impact": _truthy(it.get("high_impact")), "irreversible": _truthy(it.get("irreversible"))}
        if not _ident(node):
            errors.append(f"{tag}: before_node must be a Python identifier")
        elif node in RESERVED or node.startswith("approve_") or node.startswith("escalate_"):
            errors.append(f"{tag}: before_node collides with a scaffold name")
        if node in seen:
            errors.append(f"{tag}: declared twice; one gate per node")
        seen.add(node)
        if not g["reason"]:
            errors.append(f"{tag}: reason is missing (the approver must see why they are asked)")
        if not g["approver_role"]:
            errors.append(f"{tag}: approver_role is missing")
        if g["on_timeout"] not in ON_TIMEOUT:
            errors.append(f"{tag}: on_timeout '{g['on_timeout']}' not in {list(ON_TIMEOUT)}")
        tm = g["timeout_minutes"]
        if tm not in (None, ""):
            try:
                tmf = float(tm)
                if tmf <= 0:
                    raise ValueError
                g["timeout_minutes"] = int(tmf) if tmf == int(tmf) else tmf
            except (TypeError, ValueError):
                errors.append(f"{tag}: timeout_minutes must be a positive number, got {tm!r}")
                g["timeout_minutes"] = None
        else:
            g["timeout_minutes"] = None
        if (g["high_impact"] or g["irreversible"]) and g["timeout_minutes"] is None:
            errors.append(f"{tag}: high-impact/irreversible action needs a timeout policy (timeout_minutes + on_timeout)")
        if g["irreversible"] and g["on_timeout"] == "auto-approve":
            errors.append(f"{tag}: auto-approve on timeout is forbidden for an irreversible action")
        elif g["on_timeout"] == "auto-approve":
            warnings.append(f"{tag}: auto-approve on timeout means silence equals consent; confirm the risk owner accepts it")
        if g["on_timeout"] == "escalate" and not g["escalate_to"]:
            warnings.append(f"{tag}: on_timeout=escalate but no escalate_to role; the escalation approver is [TO BE BASELINED — owner: Process owner]")
        if g["on_timeout"] in ON_TIMEOUT and g["timeout_minutes"] is None:
            warnings.append(f"{tag}: on_timeout set but no timeout_minutes; the policy never fires")
        if not isinstance(g["editable_fields"], list):
            errors.append(f"{tag}: editable_fields must be a list")
            g["editable_fields"] = []
        g["editable_fields"] = [str(f) for f in g["editable_fields"]]
        for f in g["editable_fields"]:
            if not _ident(f):
                errors.append(f"{tag}: editable field '{f}' is not a Python identifier")
            elif declared is not None and f not in declared:
                errors.append(f"{tag}: editable field '{f}' is not in state_fields")
        gates.append(g)
    return {"graph": graph, "checkpointer": cp, "gates": gates, "errors": errors, "warnings": warnings,
            "state_fields": sorted(declared) if declared is not None else None}


# ------------------------------------------------------------------ generation

CHECKPOINTER_CODE = {
    "memory": [
        "    from langgraph.checkpoint.memory import InMemorySaver",
        "    return InMemorySaver()  # development only: paused threads are lost on restart",
    ],
    "sqlite": [
        "    import sqlite3",
        "",
        "    from langgraph.checkpoint.sqlite import SqliteSaver",
        "    path = os.environ[\"LANGGRAPH_SQLITE_PATH\"]  # set in your environment",
        "    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))",
    ],
    "postgres": [
        "    from psycopg import Connection",
        "    from psycopg.rows import dict_row",
        "",
        "    from langgraph.checkpoint.postgres import PostgresSaver",
        "    conn = Connection.connect(os.environ[\"LANGGRAPH_PG_DSN\"], autocommit=True, prepare_threshold=0, row_factory=dict_row)  # set in your environment",
        "    saver = PostgresSaver(conn)",
        "    saver.setup()  # creates checkpoint tables on first run",
        "    return saver",
    ],
}


def gen_python(v: dict, spec_name: str) -> str:
    gates = v["gates"]
    fields = sorted({f for g in gates for f in g["editable_fields"]})
    escalations = [g for g in gates if g["on_timeout"] == "escalate"]
    L = [f'"""{v["graph"]} — human-in-the-loop scaffold generated by langgraph-hitl-runner from {spec_name}.',
         "",
         "Generated as text and syntax-checked (compile/ast.parse) by langgraph-hitl-runner; it was NOT",
         "executed. Pattern per langgraph-human-in-the-loop (vendor/pins.json): interrupt() first in each",
         "approval node, Command(resume=...) to continue, a checkpointer, and one thread_id per run.",
         "Gates are wired in spec order (START -> approve_x -> x -> ... -> END): merge them into your graph.",
         '"""',
         "from __future__ import annotations", "",
         "import operator", "import os",
         "from typing import Annotated, Any, Literal", "",
         "from typing_extensions import TypedDict", "",
         "from langgraph.graph import END, START, StateGraph",
         "from langgraph.types import Command, interrupt", "", "",
         "class State(TypedDict, total=False):",
         '    """Graph state. `decisions` is an append-only audit trail of approver decisions."""', "",
         "    decisions: Annotated[list, operator.add]"]
    for f in fields:
        L.append(f"    {f}: Any  # editable by an approver")
    L += ["", "",
          "# Approval matrix as data: the single source the gates read at run time.",
          "GATES: dict[str, dict] = {"]
    for g in gates:
        L.append(f"    {g['before_node']!r}: {{")
        L.append(f"        \"reason\": {g['reason']!r},")
        L.append(f"        \"approver_role\": {g['approver_role']!r},")
        L.append(f"        \"timeout_minutes\": {g['timeout_minutes']!r},")
        L.append(f"        \"on_timeout\": {g['on_timeout']!r},")
        L.append(f"        \"escalate_to\": {g['escalate_to']!r},")
        L.append(f"        \"editable_fields\": {g['editable_fields']!r},")
        L.append(f"        \"irreversible\": {g['irreversible']!r},")
        L.append("    },")
    L += ["}", "", "",
          "def _apply_decision(gate: str, decision: dict, state: State) -> tuple[str, dict]:",
          '    """Map an approver decision to (outcome, state update). Edits outside editable_fields are refused."""',
          "    policy = GATES[gate]",
          "    kind = str(decision.get(\"decision\", \"\")).lower()",
          "    if kind == \"timeout\":",
          "        kind = {\"reject\": \"reject\", \"escalate\": \"escalate\", \"auto-approve\": \"approve\"}[policy[\"on_timeout\"]]",
          "    edits = decision.get(\"edits\") or {}",
          "    illegal = sorted(set(edits) - set(policy[\"editable_fields\"]))",
          "    if illegal:",
          "        raise ValueError(f\"{gate}: fields not editable by the approver: {illegal}\")",
          "    audit = {\"gate\": gate, \"decision\": kind, \"by\": decision.get(\"approver\"),",
          "             \"role\": policy[\"approver_role\"], \"edits\": sorted(edits)}",
          "    update: dict = {\"decisions\": [audit]}",
          "    if kind in (\"approve\", \"edit\"):",
          "        update.update(edits)",
          "        return \"approve\", update",
          "    if kind == \"escalate\":",
          "        return \"escalate\", update",
          "    return \"reject\", update", "", ""]
    for g in gates:
        n = g["before_node"]
        targets = [repr(n), '"__end__"'] + ([repr(f"escalate_{n}")] if g["on_timeout"] == "escalate" else [])
        L += [f"def approve_{n}(state: State) -> Command[Literal[{', '.join(targets)}]]:",
              f'    """Approval gate before {n}. interrupt() comes first: code above it re-runs on every resume."""',
              f"    policy = GATES[{n!r}]",
              "    decision = interrupt({",
              f"        \"gate\": {n!r},",
              "        \"reason\": policy[\"reason\"],",
              "        \"approver_role\": policy[\"approver_role\"],",
              "        \"timeout_minutes\": policy[\"timeout_minutes\"],",
              "        \"on_timeout\": policy[\"on_timeout\"],",
              "        \"editable_fields\": policy[\"editable_fields\"],",
              "        \"proposed\": {f: state.get(f) for f in policy[\"editable_fields\"]},",
              "    })",
              f"    outcome, update = _apply_decision({n!r}, decision, state)",
              "    if outcome == \"approve\":",
              f"        return Command(update=update, goto={n!r})"]
        if g["on_timeout"] == "escalate":
            L += ["    if outcome == \"escalate\":",
                  f"        return Command(update=update, goto={('escalate_' + n)!r})"]
        L += ["    return Command(update=update, goto=END)", "", ""]
        if g["on_timeout"] == "escalate":
            role = g["escalate_to"] or "[TO BE BASELINED — owner: Process owner]"
            L += [f"def escalate_{n}(state: State) -> Command[Literal[{n!r}, \"__end__\"]]:",
                  f'    """Second-level approval for {n} after a timeout; approver role: {role}."""',
                  "    decision = interrupt({",
                  f"        \"gate\": {('escalate_' + n)!r},",
                  f"        \"approver_role\": {role!r},",
                  f"        \"reason\": \"Escalated after timeout: \" + GATES[{n!r}][\"reason\"],",
                  "    })",
                  "    if str(decision.get(\"decision\", \"\")).lower() == \"approve\":",
                  f"        return Command(update={{\"decisions\": [{{\"gate\": {('escalate_' + n)!r}, \"decision\": \"approve\", \"by\": decision.get(\"approver\")}}]}}, goto={n!r})",
                  f"    return Command(update={{\"decisions\": [{{\"gate\": {('escalate_' + n)!r}, \"decision\": \"reject\", \"by\": decision.get(\"approver\")}}]}}, goto=END)",
                  "", ""]
        L += [f"def {n}(state: State) -> dict:",
              f'    """Gated action: {g["reason"]}. Runs only after approval.',
              "",
              "    Side effects belong here, after the gate, and must be idempotent (upsert, check-before-create):",
              "    a retried run must not duplicate them.",
              '    """',
              f"    raise NotImplementedError({n!r})", "", ""]
    L += ["def make_checkpointer() -> Any:",
          f'    """Checkpointer from the spec: {v["checkpointer"]}. Required for interrupt()."""']
    L += CHECKPOINTER_CODE[v["checkpointer"]]
    L += ["", "",
          "def build_graph(checkpointer: Any = None):",
          '    """Wire gates in spec order and compile WITH a checkpointer (interrupts need one)."""',
          "    builder = StateGraph(State)"]
    for g in gates:
        n = g["before_node"]
        L.append(f"    builder.add_node('approve_{n}', approve_{n})")
        L.append(f"    builder.add_node({n!r}, {n})")
        if g["on_timeout"] == "escalate":
            L.append(f"    builder.add_node('escalate_{n}', escalate_{n})")
    first = gates[0]["before_node"]
    L.append(f"    builder.add_edge(START, 'approve_{first}')")
    for a, b in zip(gates, gates[1:]):
        L.append(f"    builder.add_edge({a['before_node']!r}, 'approve_{b['before_node']}')")
    L.append(f"    builder.add_edge({gates[-1]['before_node']!r}, END)")
    L += ["    # approve_* and escalate_* route with Command(goto=...): no static out-edges, so only one branch runs",
          "    return builder.compile(checkpointer=checkpointer if checkpointer is not None else make_checkpointer())",
          "", "",
          "def _config(thread_id: str) -> dict:",
          "    return {\"configurable\": {\"thread_id\": thread_id}}", "", "",
          "def start(graph: Any, thread_id: str, initial_state: dict) -> dict:",
          '    """Start a run. The result carries `__interrupt__` when a gate is waiting."""',
          "    return graph.invoke(initial_state, _config(thread_id))", "", "",
          "def pending_approvals(result: dict) -> list:",
          '    """Interrupt payloads waiting for an approver (JSON-serializable)."""',
          "    return [i.value for i in result.get(\"__interrupt__\", [])]", "", "",
          "def resume(graph: Any, thread_id: str, decision: dict) -> dict:",
          '    """Resume handler stub: call from your approval UI/API.',
          "",
          "    decision = {\"decision\": \"approve\"|\"reject\"|\"edit\"|\"escalate\", \"approver\": <id>, \"edits\": {...}}.",
          "    Use the SAME thread_id as start(); resume only with Command(resume=...), never a plain dict",
          "    or Command(update=...). Authenticate the approver against GATES[gate][\"approver_role\"] here.",
          '    """',
          "    return graph.invoke(Command(resume=decision), _config(thread_id))", "", "",
          "def resume_on_timeout(graph: Any, thread_id: str) -> dict:",
          '    """Call from an external scheduler when a gate exceeds timeout_minutes (LangGraph has no built-in timer)."""',
          "    return graph.invoke(Command(resume={\"decision\": \"timeout\", \"approver\": \"system:timeout\"}), _config(thread_id))",
          ""]
    return "\n".join(L)


def syntax_check(src: str) -> tuple[bool, str]:
    try:
        compile(src, "hitl.py", "exec")
        ast.parse(src)
        return True, "compile() and ast.parse() succeeded"
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"


def risks(v: dict) -> list[tuple[str, str, str]]:
    """(risk, mitigation, owner) rows derived from the spec — no generic padding."""
    out = [("Paused runs lost or resumed on the wrong thread", "Persist thread_id with the business record; resume only via resume() with that id", "Engineering lead"),
           ("Side effects duplicated on resume (the node re-runs from its start)", "Keep side effects in the gated action node, after approval; make them idempotent", "Engineering lead"),
           ("Timeouts never fire: LangGraph has no built-in timer", "Schedule resume_on_timeout() per pending gate from an external job", "Platform owner")]
    if v["checkpointer"] == "memory":
        out.append(("In-memory checkpointer loses every pending approval on restart", "Switch to postgres or sqlite before any non-development use", "Platform owner"))
    for g in v["gates"]:
        n = g["before_node"]
        if g["irreversible"]:
            out.append((f"{n}: irreversible action approved in error", f"Two-person rule or confirmation step for {g['approver_role']}; on_timeout={g['on_timeout']}", "Risk owner"))
        if g["on_timeout"] == "auto-approve":
            out.append((f"{n}: silence approves the action", "Confirm the risk owner accepts auto-approve, or switch to reject", "Risk owner"))
        if g["on_timeout"] == "escalate" and not g["escalate_to"]:
            out.append((f"{n}: escalation has no named approver role", "Name escalate_to in the spec", "Process owner"))
        if g["editable_fields"]:
            out.append((f"{n}: approver edits change {', '.join(g['editable_fields'])}", "Validate edited values in the action node; edits are logged in decisions", "Engineering lead"))
    return out


def gen_markdown(v: dict, scaffold: dict, spec_name: str) -> str:
    ok = not v["errors"]
    L = [f"# Human-in-the-loop plan — {v['graph'] or '(unnamed)'}", "",
         f"Verdict: **{'VALID' if ok else 'INVALID'}** — {len(v['gates'])} gate(s), {len(v['errors'])} error(s), "
         f"{len(v['warnings'])} warning(s); checkpointer `{v['checkpointer'] or 'none'}`. Spec: `{spec_name}`. "
         "Wraps langgraph-human-in-the-loop from langchain-ai/langchain-skills (pinned in vendor/pins.json).", "",
         "## Approval matrix", "",
         "| Gate (before node) | Reason | Approver role | Timeout (min) | On timeout | Escalate to | Editable fields | High impact | Irreversible |",
         "|---|---|---|---|---|---|---|---|---|"]
    for g in v["gates"]:
        esc = g["escalate_to"] or ("[TO BE BASELINED — owner: Process owner]" if g["on_timeout"] == "escalate" else "-")
        L.append(f"| {g['before_node'] or '-'} | {g['reason'] or 'MISSING'} | {g['approver_role'] or 'MISSING'} | "
                 f"{g['timeout_minutes'] if g['timeout_minutes'] is not None else 'none'} | {g['on_timeout'] or 'MISSING'} | {esc} | "
                 f"{', '.join(g['editable_fields']) or '-'} | {'yes' if g['high_impact'] else 'no'} | {'yes' if g['irreversible'] else 'no'} |")
    L += ["", "## Validation", "", f"Scaffold: {scaffold['status']}.", ""]
    if v["errors"]:
        L += ["Errors (fix the spec and re-run):", ""] + [f"- {e}" for e in v["errors"]] + [""]
    if v["warnings"]:
        L += ["Warnings:", ""] + [f"- {w}" for w in v["warnings"]] + [""]
    if not v["errors"] and not v["warnings"]:
        L += ["No errors or warnings.", ""]
    L += ["## Resume flow", ""]
    if ok:
        L += ["1. `graph = build_graph()` compiles with the spec's checkpointer (`make_checkpointer()`).",
              "2. `result = start(graph, thread_id, initial_state)`; store `thread_id` with the business record.",
              "3. `pending_approvals(result)` returns the interrupt payload: gate, reason, approver role, timeout, editable fields, proposed values.",
              "4. The approval UI calls `resume(graph, thread_id, {\"decision\": \"approve\"|\"reject\"|\"edit\", \"approver\": ..., \"edits\": {...}})`.",
              "5. A scheduler calls `resume_on_timeout(graph, thread_id)` after `timeout_minutes`; the gate applies its `on_timeout` policy.",
              "6. Every decision is appended to `decisions` (audit trail). Rejection ends the run.",
              "",
              "`hitl.py` was generated and syntax-checked, not executed; implement the action stubs and run it where langgraph is installed."]
    else:
        L += ["No scaffold was written because the spec failed validation."]
    L += ["", "## Risks", "", "| Risk | Mitigation | Owner |", "|---|---|---|"]
    for r, m, o in risks(v):
        L.append(f"| {r} | {m} | {o} |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate approval points; emit hitl.py, hitl.md, validation.json")
    ap.add_argument("--spec", required=True, help="approval-points spec JSON (layout: assets/approvals.example.json)")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    spec_path = Path(a.spec)
    v = validate(load_spec(spec_path))
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    scaffold = {"generated": False, "syntax_checked": False, "executed": False,
                "status": "not generated (validation failed)"}
    if not v["errors"]:
        src = gen_python(v, spec_path.name)
        ok, detail = syntax_check(src)
        scaffold = {"generated": True, "syntax_checked": ok, "executed": False, "detail": detail,
                    "status": f"generated and syntax-checked ({detail}); not executed"}
        if ok:
            (out / "hitl.py").write_text(src, encoding="utf-8")
        else:
            v["errors"].append(f"generated scaffold failed the syntax check: {detail}")
    (out / "hitl.md").write_text(gen_markdown(v, scaffold, spec_path.name), encoding="utf-8")
    report = {"graph": v["graph"], "source": spec_path.name, "valid": not v["errors"],
              "checkpointer": v["checkpointer"], "errors": v["errors"], "warnings": v["warnings"],
              "gates": v["gates"], "scaffold": scaffold,
              "upstream": "langgraph-human-in-the-loop (langchain-ai/langchain-skills, vendor/pins.json)"}
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{v['graph']}: {'VALID' if report['valid'] else 'INVALID'} — {len(v['gates'])} gate(s), "
          f"{len(v['errors'])} error(s), {len(v['warnings'])} warning(s); wrote {out}")
    for e in v["errors"]:
        print(f"  error: {e}", file=sys.stderr)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
