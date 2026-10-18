"""Tests for ai-platform/prompt-spec/scripts/prompt_spec.py."""
from __future__ import annotations

import copy
import json
import math
import re

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/prompt-spec/scripts/prompt_spec.py"
FX = REPO_ROOT / "skills/ai-platform/prompt-spec/evals/fixtures"

BASE = {
    "id": "t", "version": "1.0.0", "role": "R", "task": "Q: {{q}}",
    "variables": [{"name": "q", "description": "question", "required": True}],
    "output_schema": {"type": "object", "required": ["a"],
                      "properties": {"a": {"type": "string", "enum": ["x", "y"]},
                                     "n": {"type": "integer"},
                                     "tags": {"type": "array", "items": {"type": "string"}}}},
    "constraints": ["be brief"],
    "examples": [{"inputs": {"q": "hi"}, "output": {"a": "x", "n": 2, "tags": ["k"]}}],
    "max_input_tokens": 500,
}


def _run(tmp_path, spec):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--spec", str(p), "--out-dir", str(out))
    lint = json.loads((out / "prompt-lint.json").read_text(encoding="utf-8")) if (out / "prompt-lint.json").exists() else None
    return r, lint, out


def codes(lint):
    return {f["code"] for f in lint["findings"]}


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_fixture_happy_path(tmp_path):
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--spec", str(FX / "prompt-spec.json"), "--out-dir", str(out))
    assert r.returncode == 0, r.stderr
    lint = json.loads((out / "prompt-lint.json").read_text(encoding="utf-8"))
    assert lint["status"] == "pass" and lint["summary"] == {"error": 0, "warning": 0, "info": 0}
    md = (out / "prompt.md").read_text(encoding="utf-8")
    assert md.startswith("<!-- prompt-spec: ticket-triage v1.2.0")
    assert "# Prompt ticket-triage — v1.2.0" in md and "## System" in md and "## User" in md
    assert "standard \\| priority" in md  # pipes escaped in the variables table
    cases = [json.loads(x) for x in (out / "prompt-tests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [c["id"] for c in cases] == [f"ticket-triage@1.2.0#ex-0{i}" for i in (1, 2, 3)]
    # optional variable 'channel' absent in example 2 renders empty; no placeholders survive
    assert "Channel: \n" in cases[1]["input"] and "{{" not in cases[1]["input"]
    eq = {(a["path"], json.dumps(a["value"])) for a in cases[1]["assertions"] if a["type"] == "equals"}
    assert eq == {("$.category", '"outage"'), ("$.urgency", '"high"'), ("$.needs_human", "true")}
    # token estimate is ceil(chars/4) of system + "\n" + user
    est = math.ceil((len(cases[0]["system"]) + 1 + len(cases[0]["input"])) / 4)
    assert cases[0]["input_tokens_estimate"] == est == lint["examples"][0]["tokens_estimate"]
    assert run_script(SCRIPT, "--verify-tests", str(out / "prompt-tests.jsonl")).returncode == 0


def test_broken_fixture_errors_and_no_render(tmp_path):
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--spec", str(FX / "prompt-spec-broken.json"), "--out-dir", str(out))
    assert r.returncode == 1
    lint = json.loads((out / "prompt-lint.json").read_text(encoding="utf-8"))
    assert lint["status"] == "fail" and lint["summary"]["error"] == 6 and lint["summary"]["warning"] == 1
    assert codes(lint) >= {"E-VERSION", "E-VAR-UNDECLARED", "E-VAR-UNUSED", "E-EX-MISSING-VAR", "E-EX-SCHEMA",
                           "W-EX-UNKNOWN-VAR"}
    assert not (out / "prompt.md").exists() and not (out / "prompt-tests.jsonl").exists()


def test_clean_minimal_spec(tmp_path):
    r, lint, out = _run(tmp_path, BASE)
    assert r.returncode == 0, r.stderr
    assert lint["summary"]["error"] == 0


def test_schema_validator_subset(tmp_path):
    s = copy.deepcopy(BASE)
    s["examples"] = [
        {"inputs": {"q": "1"}, "output": {"a": "z"}},                      # enum
        {"inputs": {"q": "2"}, "output": {"n": 1}},                        # required a
        {"inputs": {"q": "3"}, "output": {"a": "x", "n": 1.5}},            # integer
        {"inputs": {"q": "4"}, "output": {"a": "x", "n": True}},           # bool is not integer
        {"inputs": {"q": "5"}, "output": {"a": "x", "tags": ["ok", 3]}},   # items
        {"inputs": {"q": "6"}, "output": ["not", "object"]},               # type
        {"inputs": {"q": "7"}, "output": {"a": "y", "n": 4.0}},            # valid: 4.0 is an integer
    ]
    r, lint, _ = _run(tmp_path, s)
    assert r.returncode == 1
    msgs = [f["message"] for f in lint["findings"] if f["code"] == "E-EX-SCHEMA"]
    wheres = sorted(f["where"] for f in lint["findings"] if f["code"] == "E-EX-SCHEMA")
    assert wheres == [f"examples[{i}]" for i in range(6)]
    assert any("'z' not in enum" in m for m in msgs)
    assert any("missing required property 'a'" in m for m in msgs)
    assert any("$.n: expected type integer, got float" in m for m in msgs)
    assert any("$.n: expected type integer, got bool" in m for m in msgs)
    assert any("$.tags[1]: expected type string" in m for m in msgs)
    assert any("$: expected type object, got list" in m for m in msgs)


def test_unsupported_keyword_is_warning_and_bad_type_is_error(tmp_path):
    s = copy.deepcopy(BASE)
    s["output_schema"]["properties"]["a"]["minLength"] = 1
    r, lint, _ = _run(tmp_path, s)
    assert r.returncode == 0 and "W-SCHEMA" in codes(lint)
    s["output_schema"]["properties"]["n"]["type"] = "int"
    r, lint, _ = _run(tmp_path, s)
    assert r.returncode == 1 and "E-SCHEMA" in codes(lint)


def test_variables_both_ways_and_duplicates(tmp_path):
    s = copy.deepcopy(BASE)
    s["task"] = "Q: {{q}} {{ lang }}"
    s["variables"].append({"name": "unused", "description": "d", "required": False})
    s["variables"].append({"name": "q", "description": "d", "required": True})
    r, lint, _ = _run(tmp_path, s)
    assert r.returncode == 1
    msgs = {f["code"]: f["message"] for f in lint["findings"]}
    assert "{{lang}}" in msgs["E-VAR-UNDECLARED"]
    assert "'unused'" in msgs["E-VAR-UNUSED"]
    assert "E-VAR-DUP" in msgs


def test_token_budget(tmp_path):
    s = copy.deepcopy(BASE)
    r, lint, _ = _run(tmp_path, s)
    est = lint["examples"][0]["tokens_estimate"]
    s["max_input_tokens"] = est           # exactly at budget: ok
    r, lint, _ = _run(tmp_path, s)
    assert r.returncode == 0
    s["max_input_tokens"] = est - 1       # one under: error for the example
    r, lint, _ = _run(tmp_path, s)
    assert r.returncode == 1 and any(f["code"] == "E-BUDGET" and f["where"] == "examples[0]" for f in lint["findings"])
    assert "estimate" in lint["token_estimate_method"]


def test_missing_fields_and_semver(tmp_path):
    s = copy.deepcopy(BASE)
    del s["examples"]
    s["version"] = "v1"
    r, lint, _ = _run(tmp_path, s)
    assert r.returncode == 1 and "E-SPEC-FIELD" in codes(lint)
    s = copy.deepcopy(BASE)
    s["version"] = "1.0"
    s["examples"] = []
    r, lint, _ = _run(tmp_path, s)
    assert codes(lint) >= {"E-VERSION", "E-EX-NONE"}


def test_missing_or_invalid_spec_exits_2(tmp_path):
    assert run_script(SCRIPT, "--spec", str(tmp_path / "nope.json"), "--out-dir", str(tmp_path)).returncode == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert run_script(SCRIPT, "--spec", str(bad), "--out-dir", str(tmp_path)).returncode == 2


def test_verify_tests_rejects_bad_case(tmp_path):
    p = tmp_path / "t.jsonl"
    case = {"id": "a", "prompt_id": "t", "prompt_version": "1.0.0", "inputs": {}, "system": "s",
            "input": "Q: {{q}}", "expected": {"a": "z"}, "output_schema": BASE["output_schema"], "assertions": []}
    p.write_text(json.dumps(case) + "\n" + json.dumps(case) + "\n", encoding="utf-8")
    r = run_script(SCRIPT, "--verify-tests", str(p))
    assert r.returncode == 1
    assert "unrendered placeholder" in r.stderr and "duplicate id" in r.stderr and "fails schema" in r.stderr


def test_deterministic(tmp_path):
    a = run_script(SCRIPT, "--spec", str(FX / "prompt-spec.json"), "--out-dir", str(tmp_path / "a"))
    b = run_script(SCRIPT, "--spec", str(FX / "prompt-spec.json"), "--out-dir", str(tmp_path / "b"))
    assert a.returncode == b.returncode == 0
    for f in ("prompt.md", "prompt-lint.json", "prompt-tests.jsonl"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()


def test_offline_stdlib_only():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(socket|urllib|requests|httpx|http\.client|subprocess)\b", src, re.M)
