"""Tests for ai-platform/mcp-server-builder/scripts/scaffold_mcp.py (and the server it writes)."""
from __future__ import annotations

import json
import subprocess
import sys

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/mcp-server-builder/scripts/scaffold_mcp.py"
FX = REPO_ROOT / "skills/ai-platform/mcp-server-builder/evals/fixtures"


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_scaffold_runs_green_and_never_overwrites(tmp_path):
    target = tmp_path / "server"
    report = tmp_path / "report.json"
    r = run_script(SCRIPT, str(FX / "tools.json"), "--target", str(target), "--name", "ticket-mcp", "--report", str(report))
    assert r.returncode == 0, r.stderr
    rep = json.loads(report.read_text(encoding="utf-8"))
    assert rep["tools"] == ["search_tickets", "read_ticket"] and rep["written"] == 6 and rep["skipped"] == 0
    for rel in ("server.py", "tools/search_tickets.json", "tools/read_ticket.json", "tests/test_tools.py", "README.md"):
        assert (target / rel).is_file(), rel
    # the generated suite passes
    t = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(target / "tests")],
                       capture_output=True, text=True)
    assert t.returncode == 0, t.stdout + t.stderr
    # the server speaks JSON-RPC over stdio and stubs answer NOT_IMPLEMENTED with the schema echoed
    msgs = "\n".join(json.dumps(m) for m in [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "read_ticket", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "read_ticket", "arguments": {"ticket_id": "T000001"}}},
    ]) + "\n"
    s = subprocess.run([sys.executable, "-I", str(target / "server.py")], input=msgs, capture_output=True, text=True)
    out = [json.loads(ln) for ln in s.stdout.splitlines()]
    assert [o["id"] for o in out] == [1, 2, 3, 4]
    assert out[0]["result"]["serverInfo"]["name"] == "ticket-mcp"
    assert {t_["name"] for t_ in out[1]["result"]["tools"]} == {"search_tickets", "read_ticket"}
    assert out[2]["error"]["code"] == -32602 and "ticket_id" in out[2]["error"]["message"]
    assert out[3]["result"]["isError"] is True
    assert out[3]["result"]["structuredContent"]["schema"]["inputSchema"]["required"] == ["ticket_id"]
    # idempotent re-run
    (target / "server.py").write_text("# edited by hand\n", encoding="utf-8")
    r2 = run_script(SCRIPT, str(FX / "tools.json"), "--target", str(target))
    rep2 = json.loads(r2.stdout)
    assert r2.returncode == 0 and rep2["written"] == 0 and rep2["skipped"] == 6
    assert (target / "server.py").read_text(encoding="utf-8") == "# edited by hand\n"
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "| `search_tickets` |" in readme and "| read | stub |" in readme


def test_bad_tools_and_lang_exit_1(tmp_path):
    r = run_script(SCRIPT, str(FX / "tools-bad.json"), "--target", str(tmp_path / "s"))
    assert r.returncode == 1 and "name must match" in r.stderr and not (tmp_path / "s").exists()
    r = run_script(SCRIPT, str(FX / "tools.json"), "--target", str(tmp_path / "s"), "--lang", "typescript")
    assert r.returncode == 1 and "not supported" in r.stderr
    dup = tmp_path / "dup.json"
    dup.write_text(json.dumps([{"name": "a", "description": "x", "input_schema": {}, "output_schema": {}}] * 2), encoding="utf-8")
    assert "duplicate" in run_script(SCRIPT, str(dup), "--target", str(tmp_path / "s")).stderr
    assert run_script(SCRIPT, str(tmp_path / "nope.json"), "--target", str(tmp_path / "s")).returncode == 1
