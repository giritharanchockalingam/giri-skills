"""Tests for ai-platform/agent-architecture/scripts/design_check.py."""
from __future__ import annotations

import csv
import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/agent-architecture/scripts/design_check.py"
FX = REPO_ROOT / "skills/ai-platform/agent-architecture/evals/fixtures"


def rows(path):
    with path.open(encoding="utf-8") as f:
        return {r["item"]: r for r in csv.DictReader(f)}


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_complete_doc_and_contracts_pass(tmp_path):
    out = tmp_path / "dc.csv"
    r = run_script(SCRIPT, str(FX / "agent-design-doc.md"), str(FX / "tool-contracts.json"), "--out", str(out))
    assert r.returncode == 0, r.stderr
    rs = rows(out)
    assert len(rs) == 15 and all(x["present"] == "yes" for x in rs.values())
    assert "tool[1] update_ticket" in rs


def test_missing_hitl_and_bad_contract_exit_1(tmp_path):
    out = tmp_path / "dc.csv"
    r = run_script(SCRIPT, str(FX / "agent-design-doc-no-hitl.md"), str(FX / "tool-contracts-bad.json"), "--out", str(out))
    assert r.returncode == 1
    rs = rows(out)
    assert rs["HITL checkpoints"]["present"] == "no"
    issue = rs["tool[1] Update-Ticket"]["issue"]
    for s in ("name does not match", "missing outputSchema", "missing failure_modes",
              "x-contract.idempotent must be boolean", "x-contract missing timeout_ms"):
        assert s in issue
    assert rs["tool[0] search_tickets"]["present"] == "yes"


def test_snake_case_aliases_and_tools_wrapper(tmp_path):
    t = json.loads((FX / "tool-contracts.json").read_text(encoding="utf-8"))[0]
    t["input_schema"], t["output_schema"] = t.pop("inputSchema"), t.pop("outputSchema")
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"tools": [t]}), encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "agent-design-doc.md"), str(f), "--out", str(tmp_path / "dc.csv"))
    assert r.returncode == 0, r.stderr


def test_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, str(tmp_path / "no.md"), str(FX / "tool-contracts.json"), "--out", str(tmp_path / "x.csv")).returncode == 1
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert run_script(SCRIPT, str(FX / "agent-design-doc.md"), str(bad), "--out", str(tmp_path / "x.csv")).returncode == 1
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "agent-design-doc.md"), str(empty), "--out", str(tmp_path / "x.csv"))
    assert r.returncode == 1 and "no contracts supplied" in r.stdout + r.stderr
