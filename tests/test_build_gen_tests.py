"""Tests for build/webapp-testing-runner/scripts/gen_tests.py."""
from __future__ import annotations

import ast
import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/webapp-testing-runner/scripts/gen_tests.py"
FX = REPO_ROOT / "skills/build/webapp-testing-runner/evals/fixtures"


def gen(tmp_path, flows):
    t, r, j = tmp_path / "test_flows.py", tmp_path / "flows-report.md", tmp_path / "flows.json.out"
    res = run_script(SCRIPT, "--flows", str(flows), "--test-out", str(t), "--report", str(r), "--json", str(j))
    return res, t, (r.read_text(encoding="utf-8") if r.exists() else ""), \
        (json.loads(j.read_text(encoding="utf-8")) if j.exists() else None)


def write_flows(tmp_path, doc):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_happy_path_generates_and_compiles(tmp_path):
    res, t, report, j = gen(tmp_path, FX / "flows.json")
    assert res.returncode == 0, res.stderr
    src = t.read_text(encoding="utf-8")
    tree = ast.parse(src)
    funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    assert funcs == ["test_sign_in", "test_add_item_to_cart"]
    assert "GENERATED, NOT EXECUTED" in src
    assert src.count('page.wait_for_load_state("networkidle")') == 2          # one per goto
    assert "page.get_by_role('button', name='Sign in').click()" in src
    assert "page.get_by_label('Email').fill('pat@example.test')" in src
    assert "expect(page.get_by_test_id('cart-count')).to_contain_text('1')" in src
    assert "page.locator('ul.products > li:nth-child(2) button').click()" in src
    assert "expect(page).to_have_url(re.compile(re.escape('/dashboard')))" in src
    assert 'os.environ.get("BASE_URL", \'\')' in src                       # placeholder -> no default URL
    cov = {r["flow"]: r for r in j["coverage"]}
    assert (cov["Sign in"]["steps"], cov["Sign in"]["fill"], cov["Sign in"]["assertions"]) == (6, 2, 2)
    assert cov["Add item to cart"]["selector_kinds"] == {"css": 1, "testid": 2}
    assert j["executed"] is False and j["valid"] is True
    warn = [w for w in j["warnings"] if w["severity"] == "warning"]
    assert len(warn) == 1 and "nth-child" in warn[0]["message"] and warn[0]["step"] == 2
    for sec in ("## Flows", "## Generated tests", "## Warnings", "## How to run"):
        assert sec in report
    assert "compile() OK" in report and "not executed" in report
    assert run_script(SCRIPT, "--verify-compiles", str(t)).returncode == 0


def test_invalid_flows_exit_1_no_test_file(tmp_path):
    res, t, report, j = gen(tmp_path, FX / "flows-invalid.json")
    assert res.returncode == 1
    assert not t.exists()
    errs = j["errors"]
    assert len(errs) == 5
    assert any("unknown action 'hover'" in e for e in errs)
    assert any("fill requires a non-empty string 'value'" in e for e in errs)
    assert any("click requires a non-empty string 'selector'" in e for e in errs)
    assert any("duplicate flow name" in e for e in errs)
    assert any("steps must be a non-empty list" in e for e in errs)
    assert "**INVALID**" in report and "No tests were generated" in report


def test_selector_warnings(tmp_path):
    doc = {"base_url": "http://localhost:3000", "flows": [{"name": "s", "steps": [
        {"action": "goto", "value": "/"},
        {"action": "click", "selector": "//div[2]/button"},
        {"action": "click", "selector": ".css-1x2y3z"},
        {"action": "click", "selector": "main > div > ul > li > a"},
        {"action": "click", "selector": "#save"},
        {"action": "click", "selector": "text=Save"},
        {"action": "expect_text", "value": "Saved"}]}]}
    res, t, _, j = gen(tmp_path, write_flows(tmp_path, doc))
    assert res.returncode == 0, res.stderr
    by_step = {}
    for w in j["warnings"]:
        by_step.setdefault(w["step"], []).append(w)
    assert "XPath" in by_step[2][0]["message"]
    assert "generated class" in by_step[3][0]["message"]
    assert "long CSS chain" in by_step[4][0]["message"]
    assert by_step[5][0]["severity"] == "info"
    assert 6 not in by_step                                  # text= is a preferred selector
    assert "BASE_URL\", 'http://localhost:3000')" in t.read_text(encoding="utf-8")


def test_flow_level_warnings(tmp_path):
    doc = {"base_url": "{{BASE_URL}}", "flows": [{"name": "no asserts", "steps": [
        {"action": "click", "selector": "role=link[name=\"Home\"]"}]}]}
    res, t, _, j = gen(tmp_path, write_flows(tmp_path, doc))
    assert res.returncode == 0
    msgs = " ".join(w["message"] for w in j["warnings"])
    assert "does not start with goto" in msgs and "no expect_* step" in msgs
    assert "page.get_by_role('link', name='Home').click()" in t.read_text(encoding="utf-8")


def test_quotes_cannot_break_generated_code(tmp_path):
    doc = {"base_url": "${BASE_URL}", "flows": [{"name": "O'Brien \"quoted\" flow", "steps": [
        {"action": "goto", "value": "/a'b\"c"},
        {"action": "fill", "selector": "label=Name", "value": "x\\'); import os; os.system('rm -rf /') #"},
        {"action": "expect_text", "value": "\"\"\" end"}]}]}
    res, t, _, _ = gen(tmp_path, write_flows(tmp_path, doc))
    assert res.returncode == 0, res.stderr
    src = t.read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "system"]
    assert calls == []                                        # the payload stayed a string literal
    assert "def test_o_brien_quoted_flow(page: Page)" in src


def test_base_url_rules(tmp_path):
    bad = {"base_url": "localhost:3000", "flows": [{"name": "a", "steps": [{"action": "goto", "value": "/"}]}]}
    res, _, _, j = gen(tmp_path, write_flows(tmp_path, bad))
    assert res.returncode == 1 and "neither an http(s) URL nor a placeholder" in j["errors"][0]
    missing = {"flows": [{"name": "a", "steps": [{"action": "goto", "value": "/"}]}]}
    res, _, _, j = gen(tmp_path, write_flows(tmp_path, missing))
    assert res.returncode == 1 and "base_url missing" in j["errors"][0]


def test_verify_compiles_rejects_broken_or_unbannered(tmp_path):
    broken = tmp_path / "b.py"
    broken.write_text('"""GENERATED, NOT EXECUTED"""\ndef test_x(:\n', encoding="utf-8")
    assert run_script(SCRIPT, "--verify-compiles", str(broken)).returncode == 1
    plain = tmp_path / "p.py"
    plain.write_text("def test_x():\n    pass\n", encoding="utf-8")
    r = run_script(SCRIPT, "--verify-compiles", str(plain))
    assert r.returncode == 1 and "banner missing" in r.stderr


def test_missing_or_bad_input_exit_2(tmp_path):
    out = ("--test-out", str(tmp_path / "t.py"), "--report", str(tmp_path / "r.md"))
    assert run_script(SCRIPT, *out).returncode == 2
    assert run_script(SCRIPT, "--flows", str(tmp_path / "nope.json"), *out).returncode == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert run_script(SCRIPT, "--flows", str(bad), *out).returncode == 2
