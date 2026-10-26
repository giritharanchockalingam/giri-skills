"""Scaffolded contract tests: tools/list matches tools/*.json; stubs answer NOT_IMPLEMENTED (implemented handlers are skipped there)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import server  # noqa: E402

CONTRACTS = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((HERE.parent / "tools").glob("*.json"))}


def test_initialize_handshake():
    res = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert res["result"]["serverInfo"]["name"] == server.SERVER_NAME
    assert "tools" in res["result"]["capabilities"]
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_returns_every_tool_with_its_schema():
    res = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    listed = {t["name"]: t for t in res["result"]["tools"]}
    assert set(listed) == set(CONTRACTS) == set(server.TOOL_HANDLERS)
    for name, contract in CONTRACTS.items():
        assert listed[name]["description"] == contract["description"]
        assert listed[name]["inputSchema"] == contract["inputSchema"]
        assert listed[name]["outputSchema"] == contract["outputSchema"]


def test_call_stub_reports_not_implemented_with_schema():
    for name, contract in CONTRACTS.items():
        args = {k: None for k in (contract["inputSchema"].get("required") or [])}
        res = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                             "params": {"name": name, "arguments": args}})
        if "result" in res and not res["result"].get("isError"):
            continue  # handler implemented: cover it with its own tests
        assert res["result"]["isError"] is True
        assert res["result"]["structuredContent"]["error"]["code"] == "NOT_IMPLEMENTED"
        assert res["result"]["structuredContent"]["schema"]["inputSchema"] == contract["inputSchema"]


def test_unknown_tool_and_method_are_errors():
    assert server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                          "params": {"name": "nope", "arguments": {}}})["error"]["code"] == -32602
    assert server.handle({"jsonrpc": "2.0", "id": 5, "method": "resources/list"})["error"]["code"] == -32601
