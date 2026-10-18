#!/usr/bin/env python3
"""Scaffold a minimal, stdlib-only MCP-style server (JSON-RPC over stdio) from a tools list.

    python3 -I scripts/scaffold_mcp.py tools.json --target ./my-server [--lang python] \
        [--name my-server] [--report scaffold-report.json]

tools.json: a list (or {"tools": [...]}) of {name, description, input_schema|inputSchema,
output_schema|outputSchema}. name must match ^[a-z][a-z0-9_]*$ and be unique; schemas must be
objects. Exit 1 otherwise.

Writes under --target (created if absent):
  server.py            handles initialize, notifications/initialized, tools/list, tools/call;
                       tools/call dispatches to a stub per tool that raises NotImplementedError
                       and the server answers with isError + the tool's schema echoed
  tools/<name>.json    one contract per tool (source of truth for schemas)
  tests/test_tools.py  pytest: tools/list returns every tool with its schema; stubs report NotImplemented
  README.md            tool table, run, test, next steps
Idempotent: never overwrites an existing file (reported as skipped). The report (JSON) lists every
path with written|skipped. Only --lang python is supported; anything else exits 1. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ALIAS = {"inputSchema": ("inputSchema", "input_schema"), "outputSchema": ("outputSchema", "output_schema")}

SERVER_TEMPLATE = '''#!/usr/bin/env python3
"""{name} — minimal MCP-style server: JSON-RPC 2.0 over stdio, stdlib only.

Scaffolded by giri-skills/mcp-server-builder. Handles initialize, notifications/initialized,
tools/list and tools/call. Every tool handler is a stub that raises NotImplementedError;
replace the body in TOOL_HANDLERS, keep the contract in tools/<name>.json as the source of truth.
Run: python3 server.py   (one JSON-RPC message per line on stdin; responses on stdout; logs on stderr)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER_NAME = {name!r}
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2025-06-18"


def load_tools() -> list[dict]:
    tools = []
    for p in sorted((HERE / "tools").glob("*.json")):
        tools.append(json.loads(p.read_text(encoding="utf-8")))
    return tools


TOOLS = load_tools()
TOOL_INDEX = {{t["name"]: t for t in TOOLS}}


{handlers}

TOOL_HANDLERS = {{
{handler_map}
}}


def _error(req_id, code: int, message: str, data=None) -> dict:
    err = {{"code": code, "message": message}}
    if data is not None:
        err["data"] = data
    return {{"jsonrpc": "2.0", "id": req_id, "error": err}}


def _result(req_id, result) -> dict:
    return {{"jsonrpc": "2.0", "id": req_id, "result": result}}


def _validate_args(tool: dict, args: dict) -> str | None:
    schema = tool.get("inputSchema") or {{}}
    if not isinstance(args, dict):
        return "arguments must be an object"
    missing = [k for k in schema.get("required", []) if k not in args]
    if missing:
        return f"missing required argument(s): {{missing}}"
    if schema.get("additionalProperties") is False:
        extra = [k for k in args if k not in (schema.get("properties") or {{}})]
        if extra:
            return f"unexpected argument(s): {{extra}}"
    return None


def handle(message: dict):
    """Return a response dict, or None for notifications."""
    req_id = message.get("id")
    method = message.get("method", "")
    params = message.get("params") or {{}}
    if method == "initialize":
        return _result(req_id, {{"protocolVersion": PROTOCOL_VERSION,
                                "capabilities": {{"tools": {{"listChanged": False}}}},
                                "serverInfo": {{"name": SERVER_NAME, "version": SERVER_VERSION}}}})
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _result(req_id, {{}})
    if method == "tools/list":
        return _result(req_id, {{"tools": [
            {{k: t[k] for k in ("name", "description", "inputSchema", "outputSchema") if k in t}} for t in TOOLS]}})
    if method == "tools/call":
        name = params.get("name")
        tool = TOOL_INDEX.get(name)
        if tool is None:
            return _error(req_id, -32602, f"unknown tool: {{name}}")
        args = params.get("arguments") or {{}}
        problem = _validate_args(tool, args)
        if problem:
            return _error(req_id, -32602, f"INVALID_ARGUMENT: {{problem}}")
        try:
            out = TOOL_HANDLERS[name](args)
        except NotImplementedError as e:
            return _result(req_id, {{"isError": True, "content": [{{"type": "text", "text": f"NOT_IMPLEMENTED: {{e}}"}}],
                                    "structuredContent": {{"status": "error",
                                                          "error": {{"code": "NOT_IMPLEMENTED", "message": str(e), "retryable": False}},
                                                          "schema": {{"inputSchema": tool.get("inputSchema"),
                                                                     "outputSchema": tool.get("outputSchema")}}}}}})
        except Exception as e:  # noqa: BLE001 — never leak a stack trace to the model
            return _result(req_id, {{"isError": True, "content": [{{"type": "text", "text": "UPSTREAM_ERROR"}}],
                                    "structuredContent": {{"status": "error",
                                                          "error": {{"code": "UPSTREAM_ERROR", "message": type(e).__name__, "retryable": True}}}}}})
        return _result(req_id, {{"content": [{{"type": "text", "text": json.dumps(out)}}], "structuredContent": out}})
    if req_id is None:
        return None
    return _error(req_id, -32601, f"method not found: {{method}}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\\n")
            sys.stdout.flush()
            continue
        response = handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

HANDLER_TEMPLATE = '''def {name}(arguments: dict) -> dict:
    """{description}

    Input schema: tools/{name}.json#inputSchema. Return a dict matching outputSchema.
    """
    raise NotImplementedError("{name}: stub — implement against tools/{name}.json")
'''

TEST_TEMPLATE = '''"""Scaffolded contract tests: tools/list matches tools/*.json; stubs answer NOT_IMPLEMENTED."""
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
        assert res["result"]["isError"] is True
        assert res["result"]["structuredContent"]["error"]["code"] == "NOT_IMPLEMENTED"
        assert res["result"]["structuredContent"]["schema"]["inputSchema"] == contract["inputSchema"]


def test_unknown_tool_and_method_are_errors():
    assert server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                          "params": {"name": "nope", "arguments": {}}})["error"]["code"] == -32602
    assert server.handle({"jsonrpc": "2.0", "id": 5, "method": "resources/list"})["error"]["code"] == -32601
'''


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load_tools(path: str) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{p.name}: invalid JSON: {e}")
    if isinstance(data, dict) and "tools" in data:
        data = data["tools"]
    if not isinstance(data, list) or not data:
        die(f"{p.name}: expected a non-empty list of tools")
    tools, seen = [], set()
    for i, t in enumerate(data):
        if not isinstance(t, dict):
            die(f"tool[{i}]: not an object")
        name = t.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            die(f"tool[{i}]: name must match {NAME_RE.pattern}, got {name!r}")
        if name in seen:
            die(f"tool[{i}]: duplicate name {name!r}")
        seen.add(name)
        if not isinstance(t.get("description"), str) or not t["description"].strip():
            die(f"tool {name}: description must be a non-empty string")
        out = {"name": name, "description": t["description"].strip()}
        for canon, keys in ALIAS.items():
            val = next((t[k] for k in keys if k in t), None)
            if not isinstance(val, dict):
                die(f"tool {name}: {canon} must be an object (keys accepted: {list(keys)})")
            out[canon] = val
        for extra in ("x-contract", "failure_modes"):
            if extra in t:
                out[extra] = t[extra]
        tools.append(out)
    return tools


def write_new(path: Path, text: str, report: list[dict]) -> None:
    if path.exists():
        report.append({"path": str(path), "status": "skipped", "reason": "exists (never overwritten)"})
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    report.append({"path": str(path), "status": "written"})


def main() -> int:
    ap = argparse.ArgumentParser(description="tools.json -> minimal stdlib MCP-style server + tests + README")
    ap.add_argument("tools")
    ap.add_argument("--target", required=True, help="directory to scaffold into (created if absent)")
    ap.add_argument("--lang", default="python", help="only 'python' is supported")
    ap.add_argument("--name", default="", help="server name (default: target dir name)")
    ap.add_argument("--report", default="", help="write the scaffold report JSON here (default: stdout)")
    a = ap.parse_args()
    if a.lang != "python":
        die(f"--lang {a.lang!r} not supported; only python (stdlib) is scaffolded")
    tools = load_tools(a.tools)
    target = Path(a.target)
    if target.exists() and not target.is_dir():
        die(f"target is not a directory: {target}")
    name = a.name or target.name or "mcp-server"
    report: list[dict] = []

    handlers = "\n\n".join(HANDLER_TEMPLATE.format(name=t["name"], description=t["description"].replace('"', "'"))
                           for t in tools)
    handler_map = "\n".join(f"    {t['name']!r}: {t['name']}," for t in tools)
    write_new(target / "server.py", SERVER_TEMPLATE.format(name=name, handlers=handlers, handler_map=handler_map), report)
    for t in tools:
        write_new(target / "tools" / f"{t['name']}.json", json.dumps(t, indent=2) + "\n", report)
    write_new(target / "tests" / "__init__.py", "", report)
    write_new(target / "tests" / "test_tools.py", TEST_TEMPLATE, report)
    readme = [f"# {name}", "", "Minimal MCP-style server (JSON-RPC 2.0 over stdio, Python stdlib). Scaffolded; every tool is a stub.",
              "", "## Tools", "| Tool | Purpose | Side effect | Status |", "|---|---|---|---|"]
    readme += [f"| `{t['name']}` | {t['description']} | {(t.get('x-contract') or {}).get('side_effect', '[TO BE BASELINED — owner: MCP server owner]')} | stub |"
               for t in tools]
    readme += ["", "## Run", "```", "python3 server.py", "```",
               "One JSON-RPC message per line on stdin; responses on stdout; nothing else is written to stdout.",
               "", "## Test", "```", "python3 -m pytest -q tests", "```",
               "", "## Next steps",
               "1. Implement each handler in `server.py` against its contract in `tools/<name>.json` (source of truth).",
               "2. Add auth/scoping from the transport context (never from arguments), timeouts, rate limits, result caps.",
               "3. Work through `references/testing-checklist.md` in the mcp-server-builder skill.",
               "", "Sample data only; no credentials are read or stored by the scaffold."]
    write_new(target / "README.md", "\n".join(readme) + "\n", report)

    summary = {"server": name, "target": str(target), "lang": a.lang, "tools": [t["name"] for t in tools],
               "written": sum(r["status"] == "written" for r in report),
               "skipped": sum(r["status"] == "skipped" for r in report), "files": report}
    text = json.dumps(summary, indent=2) + "\n"
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(text, encoding="utf-8")
        print(f"scaffold: {summary['written']} written, {summary['skipped']} skipped, {len(tools)} tools -> {target}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    main()
