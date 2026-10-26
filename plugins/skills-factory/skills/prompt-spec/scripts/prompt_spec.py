#!/usr/bin/env python3
"""Lint a prompt spec, then render a versioned prompt and its regression test cases.

    python3 -I scripts/prompt_spec.py --spec prompt-spec.json --out-dir runs/x
    python3 -I scripts/prompt_spec.py --spec v2.json --previous v1.json --out-dir runs/x   # change + bump check
    python3 -I scripts/prompt_spec.py --verify-tests runs/x/prompt-tests.jsonl   # structural check

Spec JSON (assets/prompt-spec-template.json):
  id, version (semver), role, task (with {{variable}} placeholders),
  variables [{name, description, required}], output_schema (JSON Schema subset),
  constraints [str, ...], examples [{inputs: {...}, output: {...}}], max_input_tokens

Lint rules (references/lint-rules.md), each finding {code, severity, where, message}:
  * required spec fields present with the right types; version is semver; id is a slug
  * every {{variable}} in task is declared, every declared variable is used, no duplicates
  * every example supplies each required variable (unknown input keys are warnings)
  * every example output validates against output_schema (stdlib validator for the subset:
    type, properties, required, enum, items; other keywords are reported and ignored)
  * token budget: chars/4 of the rendered system + user prompt per example — an ESTIMATE,
    labelled as such — must not exceed max_input_tokens
Brownfield (--previous SPEC): the spec of the version in production. Every change is classified by its
impact on callers and consumers — major: output property or required output field removed, output type
changed, output enum value added, required variable added or made required; minor: role/task/constraint
text changed, optional variable added, variable removed or made optional, output property added, enum
value removed; patch: examples, max_input_tokens or descriptions. The version must move up by at least
the required level (E-VERSION-BUMP, E-VERSION-DOWN; a different id is E-PREV-ID). prompt-lint.json gains
"changes_vs_previous" and prompt.md a "Changes since v<previous>" section.
Then (only when no error-severity finding exists) renders:
  prompt.md          versioned system/user template with a header table
  prompt-tests.jsonl one regression case per example, ready for an eval harness
prompt-lint.json is always written. Exit 0 ok · 1 any error finding (or --verify-tests failure)
· 2 spec file missing or not valid JSON. Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
FIELDS = {"id": str, "version": str, "role": str, "task": str, "variables": list, "output_schema": dict,
          "examples": list, "max_input_tokens": int}
SCHEMA_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
SCHEMA_KEYWORDS = {"type", "properties", "required", "enum", "items", "description", "title"}
CHARS_PER_TOKEN = 4


# ------------------------------------------------------------------ JSON Schema subset

def _type_ok(value, t: str) -> bool:
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool) or (
            isinstance(value, float) and value.is_integer())
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "null":
        return value is None
    return False


def schema_problems(schema, path: str = "$") -> list[tuple[str, str, str]]:
    """Problems in the schema itself: (severity, where, message)."""
    out = []
    if not isinstance(schema, dict):
        return [("error", path, "schema node must be an object")]
    for k in schema:
        if k not in SCHEMA_KEYWORDS:
            out.append(("warning", path, f"keyword '{k}' is outside the supported subset and is ignored"))
    t = schema.get("type")
    types = t if isinstance(t, list) else ([t] if t is not None else [])
    for x in types:
        if x not in SCHEMA_TYPES:
            out.append(("error", path, f"unsupported type {x!r}"))
    if "enum" in schema and not isinstance(schema["enum"], list):
        out.append(("error", path, "enum must be a list"))
    if "required" in schema:
        req = schema["required"]
        if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
            out.append(("error", path, "required must be a list of property names"))
        else:
            props = schema.get("properties") or {}
            for r in req:
                if r not in props:
                    out.append(("warning", path, f"required property '{r}' has no entry in properties"))
    if "properties" in schema:
        if not isinstance(schema["properties"], dict):
            out.append(("error", path, "properties must be an object"))
        else:
            for k, sub in schema["properties"].items():
                out += schema_problems(sub, f"{path}.{k}")
    if "items" in schema:
        out += schema_problems(schema["items"], f"{path}[]")
    return out


def validate(value, schema, path: str = "$") -> list[str]:
    """Validate value against the subset; return violation messages (empty = valid)."""
    errs: list[str] = []
    if not isinstance(schema, dict):
        return errs
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_type_ok(value, x) for x in types):
            errs.append(f"{path}: expected type {'|'.join(types)}, got {type(value).__name__}")
            return errs
    if "enum" in schema and isinstance(schema["enum"], list) and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not in enum {schema['enum']}")
    if isinstance(value, dict):
        for r in schema.get("required") or []:
            if r not in value:
                errs.append(f"{path}: missing required property '{r}'")
        props = schema.get("properties") or {}
        if isinstance(props, dict):
            for k, sub in props.items():
                if k in value:
                    errs += validate(value[k], sub, f"{path}.{k}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            errs += validate(item, schema["items"], f"{path}[{i}]")
    return errs


# ------------------------------------------------------------------ rendering

def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def render_system(spec: dict) -> str:
    parts = [spec["role"].strip()]
    cons = [c for c in spec.get("constraints") or [] if isinstance(c, str) and c.strip()]
    if cons:
        parts += ["", "Constraints:"] + [f"- {c.strip()}" for c in cons]
    parts += ["", "Respond with JSON only, matching this schema:",
              json.dumps(spec["output_schema"], ensure_ascii=False)]
    return "\n".join(parts)


def render_user(task: str, inputs: dict | None) -> str:
    if inputs is None:
        return task.strip()

    def rep(m):
        k = m.group(1)
        if k in inputs:
            v = inputs[k]
            return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        return ""  # optional variable not supplied
    return PLACEHOLDER_RE.sub(rep, task).strip()


# ------------------------------------------------------------------ lint

def lint(spec) -> tuple[list[dict], dict]:
    """Return (findings, facts). facts holds counts and estimates used by the outputs."""
    F: list[dict] = []

    def add(code, sev, where, msg):
        F.append({"code": code, "severity": sev, "where": where, "message": msg})

    facts = {"placeholders": [], "declared": [], "examples": [], "template_tokens_estimate": None}
    if not isinstance(spec, dict):
        add("E-SPEC-TYPE", "error", "$", "spec must be a JSON object")
        return F, facts
    for k, typ in FIELDS.items():
        if k not in spec:
            add("E-SPEC-FIELD", "error", k, f"required field '{k}' missing")
        elif not isinstance(spec[k], typ) or (typ is int and isinstance(spec[k], bool)):
            add("E-SPEC-FIELD", "error", k, f"'{k}' must be {typ.__name__}")
    if "constraints" in spec and not isinstance(spec["constraints"], list):
        add("E-SPEC-FIELD", "error", "constraints", "'constraints' must be a list of strings")
    if any(f["code"] == "E-SPEC-FIELD" for f in F):
        return F, facts

    if not ID_RE.match(spec["id"]):
        add("E-ID", "error", "id", f"id {spec['id']!r} must be a lowercase slug ([a-z0-9._-])")
    if not SEMVER_RE.match(spec["version"]):
        add("E-VERSION", "error", "version", f"version {spec['version']!r} is not semver (MAJOR.MINOR.PATCH)")
    if not spec["role"].strip():
        add("E-ROLE", "error", "role", "role is empty")
    if not spec["task"].strip():
        add("E-TASK", "error", "task", "task is empty")
    if spec["max_input_tokens"] <= 0:
        add("E-BUDGET", "error", "max_input_tokens", "max_input_tokens must be > 0")
    if not [c for c in spec.get("constraints") or [] if isinstance(c, str) and c.strip()]:
        add("W-CONSTRAINTS", "warning", "constraints", "no constraints declared")
    if PLACEHOLDER_RE.search(spec["role"]):
        add("W-ROLE-VAR", "warning", "role", "placeholders in role are not filled per request; move them to task")

    # variables
    declared, required = [], set()
    for i, v in enumerate(spec["variables"]):
        where = f"variables[{i}]"
        if not isinstance(v, dict) or not isinstance(v.get("name"), str):
            add("E-VAR-DECL", "error", where, "each variable needs a string 'name'")
            continue
        n = v["name"]
        if not NAME_RE.match(n):
            add("E-VAR-NAME", "error", where, f"variable name {n!r} is not an identifier")
        if n in declared:
            add("E-VAR-DUP", "error", where, f"variable {n!r} declared twice")
        declared.append(n)
        if not isinstance(v.get("required"), bool):
            add("E-VAR-DECL", "error", where, f"variable {n!r} needs required: true|false")
        elif v["required"]:
            required.add(n)
        if not str(v.get("description") or "").strip():
            add("W-VAR-DESC", "warning", where, f"variable {n!r} has no description")
    used = []
    for m in PLACEHOLDER_RE.finditer(spec["task"]):
        n = m.group(1)
        if not NAME_RE.match(n):
            add("E-VAR-NAME", "error", "task", f"placeholder {{{{{n}}}}} is not an identifier")
        if n not in used:
            used.append(n)
    for n in used:
        if n not in declared:
            add("E-VAR-UNDECLARED", "error", "task", f"{{{{{n}}}}} is used in task but not declared in variables")
    for n in declared:
        if n not in used:
            add("E-VAR-UNUSED", "error", "variables", f"variable {n!r} is declared but never used in task")
    facts["placeholders"], facts["declared"] = used, declared

    # schema
    for sev, where, msg in schema_problems(spec["output_schema"]):
        add("E-SCHEMA" if sev == "error" else "W-SCHEMA", sev, f"output_schema {where}", msg)
    schema_ok = not any(f["code"] == "E-SCHEMA" for f in F)

    # examples + budget
    system = render_system(spec)
    template_est = estimate_tokens(system + "\n" + render_user(spec["task"], None))
    facts["template_tokens_estimate"] = template_est
    if not spec["examples"]:
        add("E-EX-NONE", "error", "examples", "no examples: nothing to regression-test")
    for i, ex in enumerate(spec["examples"]):
        where = f"examples[{i}]"
        if not isinstance(ex, dict) or not isinstance(ex.get("inputs"), dict) or "output" not in ex:
            add("E-EX-SHAPE", "error", where, "example needs an 'inputs' object and an 'output'")
            continue
        for n in sorted(required):
            if n not in ex["inputs"] or ex["inputs"][n] in (None, ""):
                add("E-EX-MISSING-VAR", "error", where, f"required variable {n!r} missing from inputs")
        for n in ex["inputs"]:
            if n not in declared:
                add("W-EX-UNKNOWN-VAR", "warning", where, f"input {n!r} is not a declared variable")
        if schema_ok:
            for err in validate(ex["output"], spec["output_schema"]):
                add("E-EX-SCHEMA", "error", where, f"output does not match output_schema: {err}")
        user = render_user(spec["task"], ex["inputs"])
        est = estimate_tokens(system + "\n" + user)
        facts["examples"].append({"index": i, "tokens_estimate": est})
        if est > spec["max_input_tokens"] > 0:
            add("E-BUDGET", "error", where,
                f"input token estimate {est} (chars/{CHARS_PER_TOKEN}) exceeds max_input_tokens {spec['max_input_tokens']}")
    return F, facts


BUMP_RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}


def _semver(v: str) -> tuple[int, int, int] | None:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(v))
    return tuple(int(x) for x in m.groups()) if m else None


def schema_changes(old, new, path: str = "$") -> list[tuple[str, str, str]]:
    """(where, change, level) for an output-schema change, judged from the consumer's side."""
    out: list[tuple[str, str, str]] = []
    if not isinstance(old, dict) or not isinstance(new, dict):
        return out if old == new else [(path, "schema replaced", "major")]
    if old.get("type") != new.get("type"):
        out.append((path, f"type {old.get('type')} -> {new.get('type')}", "major"))
    oe, ne = old.get("enum") or [], new.get("enum") or []
    for x in ne:
        if x not in oe and oe:
            out.append((path, f"enum value {x!r} added", "major"))
    for x in oe:
        if x not in ne and ne:
            out.append((path, f"enum value {x!r} removed", "minor"))
    if oe and not ne:
        out.append((path, "enum restriction removed", "major"))
    if ne and not oe:
        out.append((path, "enum restriction added", "minor"))
    op, np_ = old.get("properties") or {}, new.get("properties") or {}
    for k in np_:
        if k not in op:
            out.append((f"{path}.{k}", "property added", "minor"))
        else:
            out += schema_changes(op[k], np_[k], f"{path}.{k}")
    for k in op:
        if k not in np_:
            out.append((f"{path}.{k}", "property removed", "major"))
    orq, nrq = set(old.get("required") or []), set(new.get("required") or [])
    for k in sorted(nrq - orq):
        out.append((f"{path}.{k}", "now required", "minor"))
    for k in sorted(orq - nrq):
        out.append((f"{path}.{k}", "no longer required", "major"))
    if "items" in old or "items" in new:
        out += schema_changes(old.get("items"), new.get("items"), f"{path}[]")
    return out


def _short(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def compare_previous(spec: dict, prev: dict) -> tuple[dict, list[tuple[str, str, str]]]:
    """Change list, required and actual bump; plus findings (code, where, message) to add as errors."""
    changes: list[dict] = []

    def add(area, where, change, level):
        changes.append({"area": area, "where": where, "change": change, "level": level})

    errors: list[tuple[str, str, str]] = []
    if prev.get("id") != spec.get("id"):
        errors.append(("E-PREV-ID", "id", f"previous spec id {prev.get('id')!r} differs from {spec.get('id')!r}"))
    for k in ("role", "task"):
        if str(prev.get(k, "")).strip() != str(spec.get(k, "")).strip():
            add("instructions", k, "text changed", "minor")
    pc = [str(c).strip() for c in prev.get("constraints") or []]
    nc = [str(c).strip() for c in spec.get("constraints") or []]
    for c in nc:
        if c not in pc:
            add("instructions", "constraints", f"added: {_short(c)}", "minor")
    for c in pc:
        if c not in nc:
            add("instructions", "constraints", f"removed: {_short(c)}", "minor")
    pv = {v.get("name"): v for v in prev.get("variables") or [] if isinstance(v, dict)}
    nv = {v.get("name"): v for v in spec.get("variables") or [] if isinstance(v, dict)}
    for n, v in nv.items():
        if n not in pv:
            add("variables", n, "required variable added" if v.get("required") else "optional variable added",
                "major" if v.get("required") else "minor")
        elif bool(pv[n].get("required")) != bool(v.get("required")):
            add("variables", n, "now required" if v.get("required") else "now optional",
                "major" if v.get("required") else "minor")
        elif pv[n].get("description") != v.get("description"):
            add("variables", n, "description changed", "patch")
    for n in pv:
        if n not in nv:
            add("variables", n, "variable removed", "minor")
    for where, change, level in schema_changes(prev.get("output_schema"), spec.get("output_schema")):
        add("output_schema", where, change, level)
    if prev.get("examples") != spec.get("examples"):
        add("examples", "examples", f"{len(prev.get('examples') or [])} -> {len(spec.get('examples') or [])} example(s)", "patch")
    if prev.get("max_input_tokens") != spec.get("max_input_tokens"):
        add("budget", "max_input_tokens", f"{prev.get('max_input_tokens')} -> {spec.get('max_input_tokens')}", "patch")
    required = max((c["level"] for c in changes), key=BUMP_RANK.get, default="none")
    a, b = _semver(prev.get("version", "")), _semver(spec.get("version", ""))
    if a is None or b is None:
        actual = "unknown"
    elif b < a:
        actual = "downgrade"
    elif b == a:
        actual = "none"
    else:
        actual = "major" if b[0] > a[0] else "minor" if b[1] > a[1] else "patch"
    if actual == "downgrade":
        errors.append(("E-VERSION-DOWN", "version", f"version {spec.get('version')} is lower than previous {prev.get('version')}"))
    elif actual != "unknown" and BUMP_RANK[actual] < BUMP_RANK[required]:
        errors.append(("E-VERSION-BUMP", "version",
                       f"changes need at least a {required} bump from {prev.get('version')}; got {actual} ({spec.get('version')})"))
    return {"previous_version": prev.get("version"), "changes": changes, "required_bump": required,
            "actual_bump": actual}, errors


def render_changes_md(cv: dict) -> list[str]:
    L = ["", f"## Changes since v{cv['previous_version']}", "",
         f"{len(cv['changes'])} change(s); required bump: **{cv['required_bump']}**; actual bump: **{cv['actual_bump']}**. "
         "Levels are judged from callers (variables) and consumers (output schema)."]
    if cv["changes"]:
        L += ["", "| Area | Where | Change | Level |", "|---|---|---|---|"]
        for c in cv["changes"]:
            L.append(f"| {c['area']} | `{c['where']}` | {str(c['change']).replace('|', '/')} | {c['level']} |")
    return L


def summary(findings: list[dict]) -> dict:
    return {s: sum(f["severity"] == s for f in findings) for s in ("error", "warning", "info")}


def render_prompt_md(spec: dict, facts: dict, sha: str, cv: dict | None = None) -> str:
    L = [f"<!-- prompt-spec: {spec['id']} v{spec['version']} · spec sha256 {sha} · do not edit; edit the spec and re-render -->",
         f"# Prompt {spec['id']} — v{spec['version']}", "",
         "| Field | Value |", "|---|---|",
         f"| Prompt id | `{spec['id']}` |",
         f"| Version | {spec['version']} |",
         f"| Spec SHA-256 | `{sha}` |",
         f"| Max input tokens | {spec['max_input_tokens']} |",
         f"| Template size | {facts['template_tokens_estimate']} tokens (estimate: chars/{CHARS_PER_TOKEN}) |",
         f"| Regression cases | {len(spec['examples'])} (prompt-tests.jsonl) |", "",
         "## System", "", "```text", render_system(spec), "```", "",
         "## User", "", "```text", spec["task"].strip(), "```", "",
         "## Variables", "", "| Name | Required | Description |", "|---|---|---|"]
    for v in spec["variables"]:
        desc = str(v.get("description", "")).replace("|", "\\|")
        L.append(f"| `{{{{{v['name']}}}}}` | {'yes' if v['required'] else 'no'} | {desc} |")
    L += ["", "## Regression cases", "", "| Case | Input token estimate (chars/4) |", "|---|---|"]
    for e in facts["examples"]:
        L.append(f"| {case_id(spec, e['index'])} | {e['tokens_estimate']} |")
    if cv is not None:
        L += render_changes_md(cv)
    return "\n".join(L) + "\n"


def case_id(spec: dict, i: int) -> str:
    return f"{spec['id']}@{spec['version']}#ex-{i + 1:02d}"


def build_tests(spec: dict, facts: dict) -> list[dict]:
    system = render_system(spec)
    schema = spec["output_schema"]
    props = schema.get("properties") or {}
    out = []
    for e in facts["examples"]:
        ex = spec["examples"][e["index"]]
        user = render_user(spec["task"], ex["inputs"])
        asserts = [{"type": "json_valid"}, {"type": "json_schema"}]
        if isinstance(ex["output"], dict):
            for k in sorted(props):
                sub = props[k]
                if k in ex["output"] and isinstance(sub, dict) and ("enum" in sub or sub.get("type") == "boolean"):
                    asserts.append({"type": "equals", "path": f"$.{k}", "value": ex["output"][k]})
        out.append({
            "id": case_id(spec, e["index"]), "prompt_id": spec["id"], "prompt_version": spec["version"],
            "inputs": ex["inputs"], "system": system, "input": user,
            "expected": ex["output"], "expected_json_valid": True, "output_schema": schema,
            "assertions": asserts, "input_tokens_estimate": e["tokens_estimate"],
        })
    return out


TEST_KEYS = {"id", "prompt_id", "prompt_version", "inputs", "system", "input", "expected", "output_schema", "assertions"}


def verify_tests(path: Path) -> list[str]:
    probs, ids = [], set()
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return ["no test cases"]
    for n, ln in enumerate(lines, start=1):
        try:
            case = json.loads(ln)
        except json.JSONDecodeError as e:
            probs.append(f"line {n}: invalid JSON ({e})")
            continue
        missing = TEST_KEYS - set(case)
        if missing:
            probs.append(f"line {n}: missing keys {sorted(missing)}")
            continue
        if case["id"] in ids:
            probs.append(f"line {n}: duplicate id {case['id']}")
        ids.add(case["id"])
        if PLACEHOLDER_RE.search(case["input"]):
            probs.append(f"line {n}: unrendered placeholder in input")
        for err in validate(case["expected"], case["output_schema"]):
            probs.append(f"line {n}: expected output fails schema: {err}")
    return probs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", type=Path, help="prompt spec JSON")
    ap.add_argument("--out-dir", type=Path, help="directory for prompt.md, prompt-lint.json, prompt-tests.jsonl")
    ap.add_argument("--previous", type=Path, help="spec JSON of the version in production (change + bump check)")
    ap.add_argument("--verify-tests", type=Path, metavar="JSONL", help="structurally check a prompt-tests.jsonl")
    a = ap.parse_args(argv)
    if a.verify_tests:
        if not a.verify_tests.is_file():
            print(f"error: {a.verify_tests} not found", file=sys.stderr)
            return 2
        probs = verify_tests(a.verify_tests)
        for p in probs:
            print(f"FAIL: {p}", file=sys.stderr)
        print(f"verify-tests: {'OK' if not probs else f'{len(probs)} problem(s)'}")
        return 1 if probs else 0
    if not a.spec or not a.out_dir:
        print("error: --spec and --out-dir are required", file=sys.stderr)
        return 2
    if not a.spec.is_file():
        print(f"error: spec not found: {a.spec}", file=sys.stderr)
        return 2
    raw = a.spec.read_bytes()
    try:
        spec = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"error: spec is not valid JSON: {e}", file=sys.stderr)
        return 2
    findings, facts = lint(spec)
    cv = None
    if a.previous:
        try:
            prev = json.loads(a.previous.read_text(encoding="utf-8"))
        except FileNotFoundError:
            print(f"error: previous spec not found: {a.previous}", file=sys.stderr)
            return 2
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"error: previous spec is not valid JSON: {e}", file=sys.stderr)
            return 2
        if isinstance(spec, dict) and isinstance(prev, dict):
            cv, errs = compare_previous(spec, prev)
            findings += [{"code": c, "severity": "error", "where": w, "message": m} for c, w, m in errs]
    sev_order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (sev_order[f["severity"]], f["code"], f["where"]))
    counts = summary(findings)
    sha = hashlib.sha256(raw).hexdigest()[:12]
    ok = counts["error"] == 0
    a.out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "prompt_id": spec.get("id") if isinstance(spec, dict) else None,
        "version": spec.get("version") if isinstance(spec, dict) else None,
        "spec_sha256": sha, "status": "pass" if ok else "fail", "summary": counts,
        "token_estimate_method": f"ceil(chars / {CHARS_PER_TOKEN}) — an estimate, not a tokenizer count",
        "template_tokens_estimate": facts["template_tokens_estimate"],
        "examples": facts["examples"],
        "max_input_tokens": spec.get("max_input_tokens") if isinstance(spec, dict) else None,
        "findings": findings,
    }
    if cv is not None:
        report["changes_vs_previous"] = cv
    (a.out_dir / "prompt-lint.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not ok:
        for f in findings:
            if f["severity"] == "error":
                print(f"{f['code']} {f['where']}: {f['message']}", file=sys.stderr)
        print(f"lint failed: {counts['error']} error(s), {counts['warning']} warning(s); "
              f"prompt.md and prompt-tests.jsonl not rendered", file=sys.stderr)
        return 1
    (a.out_dir / "prompt.md").write_text(render_prompt_md(spec, facts, sha, cv), encoding="utf-8")
    tests = build_tests(spec, facts)
    with (a.out_dir / "prompt-tests.jsonl").open("w", encoding="utf-8") as f:
        for t in tests:
            f.write(json.dumps(t, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"lint passed ({counts['warning']} warning(s)); rendered {spec['id']} v{spec['version']} "
          f"with {len(tests)} regression case(s) to {a.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
