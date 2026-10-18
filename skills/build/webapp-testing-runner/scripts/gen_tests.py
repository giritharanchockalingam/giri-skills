#!/usr/bin/env python3
"""Validate user-flow JSON and generate a Playwright (pytest-playwright) test file — never executed here.

    python3 -I scripts/gen_tests.py --flows flows.json --test-out test_flows.py --report flows-report.md
    python3 -I scripts/gen_tests.py --verify-compiles test_flows.py    # compile() check only

The portal cannot launch a browser, so this skill GENERATES and statically verifies tests. It follows
the vendored webapp-testing method: native Python Playwright, headless Chromium (via pytest-playwright),
wait for `networkidle` after every navigation, descriptive selectors (role / text / label / test id).

Flows JSON:
  {"base_url": "${BASE_URL}" | "http://localhost:3000",
   "flows": [{"name": "Login", "steps": [
       {"action": "goto", "value": "/login"},
       {"action": "fill", "selector": "label=Email", "value": "user@example.test"},
       {"action": "click", "selector": "role=button[name=\\"Sign in\\"]"},
       {"action": "expect_text", "value": "Welcome"},
       {"action": "expect_url", "value": "/dashboard"}]}]}
Actions: goto(value) · click(selector) · fill(selector, value) · expect_text(value[, selector]) ·
expect_url(value). Selectors: role=<role>[name="…"] · text=… · label=… · placeholder=… · testid=… /
data-testid=… → Playwright's get_by_* locators; anything else is passed to page.locator() and gets
style warnings (nth-child/nth-of-type, XPath, generated class names, long CSS chains, bare CSS).
The base URL is read from the BASE_URL environment variable at test time; the JSON value is only a
default, and a placeholder (`${…}`, `{{…}}`, `<…>`) makes the tests skip until BASE_URL is set.

Exit codes: 0 valid flows, test file written and compiles · 1 invalid flows (report written with the
errors, no test file) or --verify-compiles failed · 2 missing input / unreadable JSON. Stdlib only;
writes only --test-out / --report / --json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ACTIONS = {"goto": ("value",), "click": ("selector",), "fill": ("selector", "value"),
           "expect_text": ("value",), "expect_url": ("value",)}
PLACEHOLDER = re.compile(r"^\s*(?:\$\{[^}]*\}|\{\{[^}]*\}\}|<[^>]*>)\s*$")
ROLE_SEL = re.compile(r'^role=(?P<role>[a-z]+)(?:\[name=(?P<q>["\'])(?P<name>.*)(?P=q)\])?$')
PREFIX_SEL = re.compile(r"^(?P<kind>text|label|placeholder|testid|data-testid)=(?P<val>.+)$")
GENERATED_CLASS = re.compile(r"\.(?:css-[a-z0-9]{4,}|sc-[A-Za-z0-9]{4,}|jsx-\d+|[a-zA-Z]+__[a-zA-Z]+-{1,2}[A-Za-z0-9]{5})")
HEADER = "GENERATED, NOT EXECUTED"


# ------------------------------------------------------------------ selectors

def classify(selector: str) -> tuple[str, str, list[str]]:
    """Return (kind, python_locator_expr, warnings) for a selector string."""
    s = selector.strip()
    m = ROLE_SEL.match(s)
    if m:
        expr = f"page.get_by_role({m['role']!r}" + (f", name={m['name']!r})" if m["name"] is not None else ")")
        return "role", expr, []
    m = PREFIX_SEL.match(s)
    if m:
        kind = {"data-testid": "testid"}.get(m["kind"], m["kind"])
        val = m["val"].strip().strip("\"'")
        fn = {"text": "get_by_text", "label": "get_by_label", "placeholder": "get_by_placeholder",
              "testid": "get_by_test_id"}[kind]
        return kind, f"page.{fn}({val!r})", []
    warns = []
    kind = "css"
    if s.startswith("xpath=") or s.startswith("//") or s.startswith("(//"):
        kind = "xpath"
        warns.append("XPath selector: brittle against markup changes; prefer role/text/test id")
    if re.search(r":nth-(?:child|of-type)\(", s):
        warns.append("positional selector (nth-child/nth-of-type): breaks when order changes; prefer role/text/test id")
    if GENERATED_CLASS.search(s):
        warns.append("generated class name (CSS-in-JS/module hash): changes between builds; prefer a test id")
    if kind == "css" and len(re.findall(r"\s*[> ~+]\s*", s.strip())) >= 3:
        warns.append("long CSS chain couples the test to DOM structure; prefer role/text/test id")
    if not warns:
        warns.append("CSS selector: acceptable, but role/text/label/test id survive refactors better")
    return kind, f"page.locator({s!r})", warns


# ------------------------------------------------------------------ validation

def validate(doc) -> tuple[list[str], list[dict]]:
    """Return (errors, warnings). Warnings are {flow, step, message, severity}."""
    errors, warns = [], []
    if not isinstance(doc, dict):
        return ["top level must be a JSON object with base_url and flows"], []
    bu = doc.get("base_url")
    if not isinstance(bu, str) or not bu.strip():
        errors.append("base_url missing: give a URL or a placeholder such as ${BASE_URL}")
    elif not PLACEHOLDER.match(bu) and not re.match(r"^https?://", bu):
        errors.append(f"base_url {bu!r} is neither an http(s) URL nor a placeholder")
    flows = doc.get("flows")
    if not isinstance(flows, list) or not flows:
        errors.append("flows must be a non-empty list")
        return errors, warns
    names = set()
    for fi, flow in enumerate(flows, 1):
        where = f"flow {fi}"
        if not isinstance(flow, dict):
            errors.append(f"{where}: must be an object with name and steps")
            continue
        name = flow.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{where}: name missing")
        else:
            where = f"flow {fi} ({name})"
            key = slug(name)
            if key in names:
                errors.append(f"{where}: duplicate flow name (test function names must be unique)")
            names.add(key)
        steps = flow.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{where}: steps must be a non-empty list")
            continue
        for si, st in enumerate(steps, 1):
            sw = f"{where} step {si}"
            if not isinstance(st, dict):
                errors.append(f"{sw}: must be an object")
                continue
            act = st.get("action")
            if act not in ACTIONS:
                errors.append(f"{sw}: unknown action {act!r} (known: {', '.join(ACTIONS)})")
                continue
            for field in ACTIONS[act]:
                v = st.get(field)
                if not isinstance(v, str) or not v.strip():
                    errors.append(f"{sw}: {act} requires a non-empty string '{field}'")
            for field in ("selector", "value"):
                if field in st and not isinstance(st[field], str):
                    errors.append(f"{sw}: '{field}' must be a string")
            if isinstance(st.get("selector"), str) and st["selector"].strip():
                if act in ("goto", "expect_url"):
                    warns.append({"flow": name, "step": si, "severity": "info",
                                  "message": f"{act} ignores 'selector'"})
                else:
                    _, _, sel_w = classify(st["selector"])
                    for w in sel_w:
                        warns.append({"flow": name, "step": si, "severity": "info" if w.startswith("CSS selector:")
                                      else "warning", "message": f"{st['selector']!r}: {w}"})
        if isinstance(steps[0], dict) and steps[0].get("action") != "goto":
            warns.append({"flow": name, "step": 1, "severity": "warning",
                          "message": "flow does not start with goto: it depends on the page another test left open"})
        if not any(isinstance(s, dict) and str(s.get("action", "")).startswith("expect_") for s in steps):
            warns.append({"flow": name, "step": "-", "severity": "warning",
                          "message": "flow has no expect_* step: it can pass without checking anything"})
    return errors, warns


# ------------------------------------------------------------------ generation

def slug(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip().lower()).strip("_")
    return s if s and not s[0].isdigit() else f"flow_{s}"


def gen_step(st: dict) -> list[str]:
    act = st["action"]
    if act == "goto":
        return [f"page.goto(_url({st['value']!r}))", 'page.wait_for_load_state("networkidle")']
    if act == "click":
        _, loc, _ = classify(st["selector"])
        return [f"{loc}.click()"]
    if act == "fill":
        _, loc, _ = classify(st["selector"])
        return [f"{loc}.fill({st['value']!r})"]
    if act == "expect_text":
        if st.get("selector", "").strip():
            _, loc, _ = classify(st["selector"])
            return [f"expect({loc}).to_contain_text({st['value']!r})"]
        return [f"expect(page.get_by_text({st['value']!r}).first).to_be_visible()"]
    if act == "expect_url":
        return [f"expect(page).to_have_url(re.compile(re.escape({st['value']!r})))"]
    raise ValueError(act)


def generate(doc: dict, source: str) -> str:
    bu = doc["base_url"].strip()
    default = "" if PLACEHOLDER.match(bu) else bu
    out = [
        f'"""Playwright tests for {len(doc["flows"])} user flow(s) from {source}.',
        "",
        f"{HEADER}: generated by webapp-testing-runner (giri-skills); the generator verified that this file",
        "compiles, but no browser was launched and no test was run. Run it yourself:",
        "    pip install pytest-playwright && playwright install chromium",
        "    BASE_URL=<your app url> pytest test_flows.py",
        '"""',
        "import os",
        "import re",
        "",
        "import pytest",
        "from playwright.sync_api import Page, expect",
        "",
        f"BASE_URL = os.environ.get(\"BASE_URL\", {default!r}).rstrip(\"/\")",
        "",
        "",
        "def _url(path: str) -> str:",
        '    return path if re.match(r"^https?://", path) else BASE_URL + "/" + path.lstrip("/")',
        "",
        "",
        "@pytest.fixture(autouse=True)",
        "def _require_base_url() -> None:",
        "    if not BASE_URL:",
        '        pytest.skip("set BASE_URL to the app under test")',
    ]
    for flow in doc["flows"]:
        steps = flow["steps"]
        out += ["", "", f"def test_{slug(flow['name'])}(page: Page) -> None:",
                f"    {('Flow: ' + flow['name'] + f' ({len(steps)} steps).')!r}"]
        for i, st in enumerate(steps, 1):
            out.append(f"    # step {i}: {st['action']}")
            out += [f"    {ln}" for ln in gen_step(st)]
    return "\n".join(out) + "\n"


def coverage(doc: dict) -> list[dict]:
    rows = []
    for flow in doc["flows"]:
        counts = {a: 0 for a in ACTIONS}
        kinds: dict[str, int] = {}
        for st in flow["steps"]:
            counts[st["action"]] += 1
            if st.get("selector") and st["action"] not in ("goto", "expect_url"):
                k, _, _ = classify(st["selector"])
                kinds[k] = kinds.get(k, 0) + 1
        rows.append({"flow": flow["name"], "test": f"test_{slug(flow['name'])}", "steps": len(flow["steps"]),
                     **counts, "assertions": counts["expect_text"] + counts["expect_url"], "selector_kinds": kinds})
    return rows


def compiles(src: str, name: str = "test_flows.py") -> tuple[bool, str]:
    try:
        compile(src, name, "exec")
        return True, "compile() OK"
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"


# ------------------------------------------------------------------ report

def _cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_report(doc, errors, warns, cov, compiled, source) -> str:
    banner = (f"Tests were **{HEADER.lower()}**: the file was generated and checked with compile(); "
              "no browser was launched." if compiled and compiled[0] else
              "No tests were generated (invalid flows) and nothing was executed.")
    out = ["# Flows report", "", f"_Generated by webapp-testing-runner from {_cell(source)}. {banner}_", ""]
    out += ["## Flows", ""]
    if errors:
        out += [f"**INVALID** — {len(errors)} error(s); no test file was generated.", ""]
        out += [f"- {e}" for e in errors] + [""]
    flows = doc.get("flows") if isinstance(doc, dict) and isinstance(doc.get("flows"), list) else []
    if cov:
        out += ["Coverage matrix (steps per action, per flow):", "",
                "| Flow | Test | Steps | goto | click | fill | expect_text | expect_url | Assertions | Selector kinds |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for r in cov:
            kinds = ", ".join(f"{k}×{n}" for k, n in sorted(r["selector_kinds"].items())) or "—"
            out.append(f"| {_cell(r['flow'])} | `{r['test']}` | {r['steps']} | {r['goto']} | {r['click']} | "
                       f"{r['fill']} | {r['expect_text']} | {r['expect_url']} | {r['assertions']} | {kinds} |")
        out.append("")
    elif not errors:
        out += [f"{len(flows)} flow(s).", ""]
    out += ["## Generated tests", ""]
    if compiled is None:
        out += ["None — fix the errors under Flows and re-run.", ""]
    else:
        ok, msg = compiled
        out += [f"- File: `test_flows.py` ({len(cov)} test function(s), pytest-playwright `page` fixture)",
                f"- Static check: {msg}" if ok else f"- Static check FAILED: {msg}",
                f"- Execution: not run ({HEADER.lower()}); results exist only after you run it", ""]
    out += ["## Warnings", ""]
    if warns:
        out += ["| Flow | Step | Severity | Warning |", "|---|---|---|---|"]
        out += [f"| {_cell(w['flow'])} | {w['step']} | {w['severity']} | {_cell(w['message'])} |" for w in warns]
        out.append("")
    else:
        out += ["None.", ""]
    bu = doc.get("base_url", "") if isinstance(doc, dict) else ""
    out += ["## How to run", "",
            "```bash",
            "pip install pytest-playwright",
            "playwright install chromium",
            "BASE_URL=<your app url> pytest test_flows.py      # headless Chromium by default",
            "# server not running yet? use the upstream helper (vendor/webapp-testing/scripts/with_server.py):",
            'python vendor/webapp-testing/scripts/with_server.py --server "npm run dev" --port 5173 -- \\',
            "  env BASE_URL=http://localhost:5173 pytest test_flows.py",
            "```", "",
            f"base_url in the flows file: `{_cell(bu)}`"
            + (" (placeholder — tests skip until BASE_URL is set)" if isinstance(bu, str) and PLACEHOLDER.match(bu) else ""),
            ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="User flows JSON -> validated pytest-playwright test file (not executed)")
    ap.add_argument("--flows", help="flows JSON (layout: assets/flows-template.json)")
    ap.add_argument("--test-out", help="write the generated test file here (test_flows.py)")
    ap.add_argument("--report", help="write flows-report.md here")
    ap.add_argument("--json", dest="json_out", help="optional: write the validation/coverage result as JSON")
    ap.add_argument("--verify-compiles", metavar="PY", help="only check that a generated file compiles")
    a = ap.parse_args()
    if a.verify_compiles:
        p = Path(a.verify_compiles)
        if not p.is_file():
            print(f"verify: {p} missing", file=sys.stderr)
            return 1
        src = p.read_text(encoding="utf-8")
        ok, msg = compiles(src, p.name)
        if ok and HEADER not in src:
            ok, msg = False, f"'{HEADER}' banner missing"
        print(f"verify: {msg}", file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    if not a.flows or not Path(a.flows).is_file():
        print(f"error: --flows is required and must exist (got {a.flows!r})", file=sys.stderr)
        return 2
    if not a.test_out or not a.report:
        print("error: give --test-out and --report", file=sys.stderr)
        return 2
    try:
        doc = json.loads(Path(a.flows).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"error: flows file is not valid JSON: {e}", file=sys.stderr)
        return 2
    source = Path(a.flows).name
    errors, warns = validate(doc)
    cov, compiled = [], None
    if not errors:
        cov = coverage(doc)
        src = generate(doc, source)
        compiled = compiles(src)
        if compiled[0]:
            Path(a.test_out).write_text(src, encoding="utf-8")
        else:
            errors.append(f"generated file does not compile: {compiled[1]}")
    Path(a.report).write_text(render_report(doc, errors, warns, cov, compiled, source), encoding="utf-8")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps({"valid": not errors, "errors": errors, "warnings": warns,
                                                "coverage": cov, "executed": False}, indent=2) + "\n", encoding="utf-8")
    if errors:
        for e in errors:
            print(f"invalid: {e}", file=sys.stderr)
        return 1
    print(f"generated {len(cov)} test(s), {len(warns)} warning(s); compiled OK; not executed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
