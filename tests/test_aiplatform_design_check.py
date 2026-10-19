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


# ---------------------------------------------------------------- existing agent: --answers cross-check

def test_existing_agent_doc_matches_tree(tmp_path):
    out = tmp_path / "dc.csv"
    r = run_script(SCRIPT, str(FX / "agent-design-doc-existing.md"), str(FX / "tool-contracts-existing.json"),
                   "--answers", str(FX / "answers-existing.json"), "--out", str(out))
    assert r.returncode == 0, r.stderr
    rs = rows(out)
    assert len(rs) == 16 and all(x["present"] == "yes" for x in rs.values())
    assert rs["Pattern matches decision tree"]["kind"] == "doc"
    assert "tool[1] issue_credit_note" in rs


def test_existing_doc_pattern_drift_is_a_gap(tmp_path):
    # the live doc declares Generator + evaluator; answers that say a single agent fits give Single agent
    out = tmp_path / "dc.csv"
    r = run_script(SCRIPT, str(FX / "agent-design-doc-existing.md"), str(FX / "tool-contracts-existing.json"),
                   "--answers", str(FX / "answers.json"), "--out", str(out))
    assert r.returncode == 1
    row = rows(out)["Pattern matches decision tree"]
    assert row["present"] == "no"
    assert row["issue"] == "doc declares Generator + evaluator; decision tree gives Single agent"


def test_pattern_check_needs_decision_line(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text((FX / "agent-design-doc.md").read_text(encoding="utf-8").replace("**Decision:**", "Decision:"),
                   encoding="utf-8")
    out = tmp_path / "dc.csv"
    r = run_script(SCRIPT, str(doc), str(FX / "tool-contracts.json"), "--answers", str(FX / "answers.json"),
                   "--out", str(out))
    assert r.returncode == 1
    assert rows(out)["Pattern matches decision tree"]["issue"].startswith("no `**Decision:**` line to compare")


def test_answers_invalid_or_missing_exit_1(tmp_path):
    bad = tmp_path / "a.json"
    bad.write_text(json.dumps({"q1_steps_enumerable": "maybe"}), encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "agent-design-doc.md"), str(FX / "tool-contracts.json"), "--answers", str(bad),
                   "--out", str(tmp_path / "x.csv"))
    assert r.returncode == 1 and "unanswered" in r.stderr
    r = run_script(SCRIPT, str(FX / "agent-design-doc.md"), str(FX / "tool-contracts.json"),
                   "--answers", str(tmp_path / "none.json"), "--out", str(tmp_path / "x.csv"))
    assert r.returncode == 1 and "answers not found" in r.stderr


def test_without_answers_rows_unchanged(tmp_path):
    out = tmp_path / "dc.csv"
    run_script(SCRIPT, str(FX / "agent-design-doc-existing.md"), str(FX / "tool-contracts-existing.json"), "--out", str(out))
    assert "Pattern matches decision tree" not in rows(out)
