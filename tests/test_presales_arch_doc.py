"""Tests for presales/solution-architecture-doc/scripts/arch_doc.py."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/solution-architecture-doc/scripts/arch_doc.py"
FX = REPO_ROOT / "skills/presales/solution-architecture-doc/evals/fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_output  # noqa: E402


def run(tmp_path, comp):
    md, nfr = tmp_path / "arch.md", tmp_path / "nfr.csv"
    return run_script(SCRIPT, str(comp), "--out", str(md), "--nfr", str(nfr)), md, nfr


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_fixture_doc(tmp_path):
    r, md, nfr = run(tmp_path, FX / "components.json")
    assert r.returncode == 0, r.stderr
    text = md.read_text(encoding="utf-8")
    assert text.count("```mermaid") == 2
    assert check_output.run_check("mermaid_parses", str(md))["pass"]
    assert 'SYS["Order Hub"]' in text and 'erp -->|batch file: inventory positions| SYS' in text
    assert "gw -->|INT-001 sync REST| orders" in text and 'subgraph Order_Hub["Order Hub"]' in text
    assert "### event" in text and "| INT-004 | Event backbone | Warehouse management | connector |" in text
    assert "| 2 | INT-004, INT-005 | batch file, event |" in text
    assert "| ADR-005 | API gateway on Apigee X |" in text
    rows = list(csv.DictReader(nfr.open(encoding="utf-8")))
    assert [r_["category"] for r_ in rows] == ["Availability", "Performance", "Recoverability", "Security"]
    assert rows[0]["target"] == "99.9% monthly" and rows[1]["target"] == "[TO BE BASELINED — owner: Solution architect]"
    assert "| Wave for INT-006 |" in text                               # missing wave surfaced


def test_thin_components_parse_and_mark_tbd(tmp_path):
    r, md, nfr = run(tmp_path, FX / "components-thin.json")
    assert r.returncode == 0, r.stderr
    assert check_output.run_check("mermaid_parses", str(md))["pass"]
    rows = list(csv.DictReader(nfr.open(encoding="utf-8")))
    assert all(r_["target"].startswith("[TO BE BASELINED") for r_ in rows)


def test_labels_are_mermaid_safe(tmp_path):
    comp = tmp_path / "c.json"
    comp.write_text(json.dumps({"system": "Sys (v2) [beta]", "containers": [{"id": "a", "name": "A {core}", "tech": "x(y)"}],
                                "integrations": []}), encoding="utf-8")
    r, md, _ = run(tmp_path, comp)
    assert r.returncode == 0, r.stderr
    assert check_output.run_check("mermaid_parses", str(md))["pass"]


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.json")[0].returncode == 1
    for bad in ('{nope', '{"system": "x"}', '{"system": "x", "containers": [{"id": "a", "name": "A"}, {"id": "a", "name": "B"}]}',
                '{"system": "x", "containers": [{"id": "a", "name": "A"}], "integrations": [{"from": "a", "to": "zzz"}]}'):
        p = tmp_path / "b.json"
        p.write_text(bad, encoding="utf-8")
        assert run(tmp_path, p)[0].returncode == 1, bad
