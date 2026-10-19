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


# --- brownfield: extend a server that already runs (--from-existing) ---

def _extend(tmp_path, tools="tools-v2.json", src=None, target=None):
    target = target or tmp_path / "server"
    rep = tmp_path / "rep.json"
    r = run_script(SCRIPT, str(FX / tools), "--target", str(target), "--from-existing",
                   str(src or FX / "existing-server"), "--report", str(rep))
    return r, target, (json.loads(rep.read_text()) if rep.exists() else None)


def _pytest(target):
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(target / "tests")],
                          capture_output=True, text=True)


def test_extend_adds_missing_tools_and_keeps_implemented_handler(tmp_path):
    r, target, rep = _extend(tmp_path)
    assert r.returncode == 0, r.stderr
    assert rep["added_tools"] == ["add_comment", "close_ticket"]
    assert rep["contract_changed"] == [{"name": "read_ticket", "keys": ["x-contract"]}]
    assert rep["existing_only_tools"] == []
    server = (target / "server.py").read_text()
    assert "SAMPLE_TICKETS" in server and "def add_comment(arguments: dict)" in server
    deployed = json.loads((target / "tools/read_ticket.json").read_text())
    assert deployed["x-contract"]["timeout_ms"] == 3000  # drift reported, never overwritten
    readme = (target / "README.md").read_text()
    assert readme.index("`close_ticket`") > readme.index("`read_ticket`") > 0
    assert _pytest(target).returncode == 0
    assert (FX / "existing-server/server.py").read_text().count("def add_comment") == 0  # source untouched


def test_extend_twice_is_idempotent(tmp_path):
    r, target, _ = _extend(tmp_path)
    assert r.returncode == 0
    before = (target / "server.py").read_text()
    r, _, rep = _extend(tmp_path, src=target, target=target)  # in place
    assert r.returncode == 0, r.stderr
    assert rep["added_tools"] == [] and (target / "server.py").read_text() == before


def test_extend_reports_tools_only_in_server(tmp_path):
    r, _, rep = _extend(tmp_path, tools="tools.json")
    assert r.returncode == 0
    assert rep["added_tools"] == [] and rep["existing_only_tools"] == []
    one = tmp_path / "one.json"
    one.write_text(json.dumps([json.loads((FX / "existing-server/tools/search_tickets.json").read_text())]))
    rep_path = tmp_path / "r2.json"
    r = run_script(SCRIPT, str(one), "--target", str(tmp_path / "s2"), "--from-existing", str(FX / "existing-server"),
                   "--report", str(rep_path))
    assert r.returncode == 0, r.stderr
    assert json.loads(rep_path.read_text())["existing_only_tools"] == ["read_ticket"]


def test_extend_refuses_non_empty_target_and_foreign_server(tmp_path):
    target = tmp_path / "server"
    target.mkdir()
    (target / "x.txt").write_text("keep")
    r, _, _ = _extend(tmp_path, target=target)
    assert r.returncode == 1 and "must be empty" in r.stderr
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "server.py").write_text("print('hi')\n")
    r, _, _ = _extend(tmp_path, src=foreign, target=tmp_path / "t3")
    assert r.returncode == 1 and "not a server scaffolded by this skill" in r.stderr
