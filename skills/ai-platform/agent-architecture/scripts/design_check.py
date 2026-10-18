#!/usr/bin/env python3
"""Gate an agent design doc and its tool contracts before build.

    python3 -I scripts/design_check.py agent-design-doc.md tool-contracts.json \
        --out design-check.csv [--schema assets/tool-contract.schema.json]

Doc (assets/agent-design-doc.md layout): every required section heading must be present
(Job and success metric, Pattern decision, State schema, Graph, Tool contracts, HITL checkpoints,
Failure modes, Budgets, Observability, Security, Open questions), plus a `**Decision:**` line and
one ```mermaid block under Graph.

Contracts: a JSON list (or {"tools": [...]}) of tool contracts. Each must carry name, description,
inputSchema|input_schema, outputSchema|output_schema, failure_modes (non-empty list) and the
schema's required keys (x-contract with side_effect, idempotent, scopes, timeout_ms). Types are
checked minimally against the schema's `type` per property (string / object / array / boolean /
integer). No JSON-Schema library: required keys + top-level types only.

Writes design-check.csv: item, kind (section|doc|contract), present (yes|no), issue.
Exit 1 when any required section is missing or any contract is invalid; exit 0 otherwise.
Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
REQUIRED_SECTIONS = ["Job and success metric", "Pattern decision", "State schema", "Graph", "Tool contracts",
                     "HITL checkpoints", "Failure modes", "Budgets", "Observability", "Security", "Open questions"]
ALIASES = {"inputSchema": ("inputSchema", "input_schema"), "outputSchema": ("outputSchema", "output_schema")}
TYPES = {"string": str, "object": dict, "array": list, "boolean": bool, "integer": int, "number": (int, float)}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load_json(path: Path, what: str):
    if not path.is_file():
        die(f"{what} not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path.name}: invalid JSON: {e}")


def check_doc(text: str) -> list[dict]:
    rows = []
    heads = [ln.lstrip("#").strip().lower() for ln in text.splitlines() if ln.startswith("#")]
    for sec in REQUIRED_SECTIONS:
        ok = any(sec.lower() in h for h in heads)
        rows.append({"item": sec, "kind": "section", "present": "yes" if ok else "no",
                     "issue": "" if ok else "required section heading missing"})
    has_decision = bool(re.search(r"^\*\*Decision:\*\*\s*\S", text, re.M))
    rows.append({"item": "Decision line", "kind": "doc", "present": "yes" if has_decision else "no",
                 "issue": "" if has_decision else "no `**Decision:** <pattern> because <criterion>` line"})
    has_mermaid = "```mermaid" in text
    rows.append({"item": "Graph diagram", "kind": "doc", "present": "yes" if has_mermaid else "no",
                 "issue": "" if has_mermaid else "no ```mermaid block"})
    return rows


def _get(tool: dict, key: str):
    for k in ALIASES.get(key, (key,)):
        if k in tool:
            return k, tool[k]
    return key, None


def check_contract(tool, idx: int, schema: dict) -> dict:
    name = tool.get("name") if isinstance(tool, dict) else None
    label = f"tool[{idx}] {name or '?'}"
    if not isinstance(tool, dict):
        return {"item": label, "kind": "contract", "present": "no", "issue": "contract is not an object"}
    issues = []
    required = list(schema.get("required") or []) + ["failure_modes"]
    props = schema.get("properties") or {}
    for key in required:
        k, val = _get(tool, key)
        if val is None:
            issues.append(f"missing {key}")
            continue
        want = (props.get(key) or {}).get("type") if key != "failure_modes" else "array"
        if want in TYPES and not isinstance(val, TYPES[want]) or (want == "integer" and isinstance(val, bool)):
            issues.append(f"{k} must be {want}")
        elif key == "failure_modes" and not val:
            issues.append("failure_modes is empty")
        elif key == "name":
            pat = (props.get("name") or {}).get("pattern")
            if pat and not re.fullmatch(pat, str(val)):
                issues.append(f"name does not match {pat}")
    xc, xreq = tool.get("x-contract"), ((props.get("x-contract") or {}).get("required") or [])
    if isinstance(xc, dict):
        xprops = (props.get("x-contract") or {}).get("properties") or {}
        for key in xreq:
            if key not in xc:
                issues.append(f"x-contract missing {key}")
                continue
            want = (xprops.get(key) or {}).get("type")
            if want in TYPES and (not isinstance(xc[key], TYPES[want]) or (want == "integer" and isinstance(xc[key], bool))):
                issues.append(f"x-contract.{key} must be {want}")
            enum = (xprops.get(key) or {}).get("enum")
            if enum and xc[key] not in enum:
                issues.append(f"x-contract.{key} must be one of {enum}")
    return {"item": label, "kind": "contract", "present": "yes" if not issues else "no", "issue": "; ".join(issues)}


def main() -> int:
    ap = argparse.ArgumentParser(description="agent design doc + tool contracts -> design-check.csv (exit 1 on gaps)")
    ap.add_argument("doc")
    ap.add_argument("contracts")
    ap.add_argument("--out", required=True)
    ap.add_argument("--schema", default=str(SKILL / "assets" / "tool-contract.schema.json"))
    a = ap.parse_args()
    doc = Path(a.doc)
    if not doc.is_file():
        die(f"design doc not found: {doc}")
    contracts = load_json(Path(a.contracts), "tool contracts")
    if isinstance(contracts, dict) and "tools" in contracts:
        contracts = contracts["tools"]
    if not isinstance(contracts, list):
        die("tool contracts must be a JSON list (or {\"tools\": [...]})")
    schema = load_json(Path(a.schema), "schema")

    rows = check_doc(doc.read_text(encoding="utf-8"))
    if not contracts:
        rows.append({"item": "tool contracts", "kind": "contract", "present": "no", "issue": "no contracts supplied"})
    rows += [check_contract(t, i, schema) for i, t in enumerate(contracts)]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["item", "kind", "present", "issue"])
        w.writeheader()
        w.writerows(rows)
    failures = [r for r in rows if r["present"] == "no"]
    print(f"design check: {len(rows) - len(failures)}/{len(rows)} items present -> {out}")
    for r in failures:
        print(f"  GAP {r['kind']}: {r['item']} — {r['issue']}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
