#!/usr/bin/env python3
"""ticket-mcp — FICTIONAL FIXTURE (server as deployed today, v0.1, search_tickets implemented) — minimal MCP-style server: JSON-RPC 2.0 over stdio, stdlib only.

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
SERVER_NAME = 'ticket-mcp'
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2025-06-18"


def load_tools() -> list[dict]:
    tools = []
    for p in sorted((HERE / "tools").glob("*.json")):
        tools.append(json.loads(p.read_text(encoding="utf-8")))
    return tools


TOOLS = load_tools()
TOOL_INDEX = {t["name"]: t for t in TOOLS}


SAMPLE_TICKETS = [  # fictional sample data for the fixture; no real customer records
    {"id": "T000101", "status": "open", "subject": "Cannot log in"},
    {"id": "T000102", "status": "closed", "subject": "Invoice copy"},
]


def search_tickets(arguments: dict) -> dict:
    """Search support tickets by status and date. Use before reading or updating a ticket.

    Implemented (fictional fixture): filters the sample tickets by status.
    """
    limit = arguments.get("limit") or 20
    items = [t for t in SAMPLE_TICKETS if t["status"] == arguments.get("status")][:limit]
    return {"status": "ok", "data": {"items": items, "total": len(items)}}


def read_ticket(arguments: dict) -> dict:
    """Read one ticket by id.

    Input schema: tools/read_ticket.json#inputSchema. Return a dict matching outputSchema.
    """
    raise NotImplementedError("read_ticket: stub — implement against tools/read_ticket.json")


TOOL_HANDLERS = {
    'search_tickets': search_tickets,
    'read_ticket': read_ticket,
}


def _error(req_id, code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _result(req_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _validate_args(tool: dict, args: dict) -> str | None:
    schema = tool.get("inputSchema") or {}
    if not isinstance(args, dict):
        return "arguments must be an object"
    missing = [k for k in schema.get("required", []) if k not in args]
    if missing:
        return f"missing required argument(s): {missing}"
    if schema.get("additionalProperties") is False:
        extra = [k for k in args if k not in (schema.get("properties") or {})]
        if extra:
            return f"unexpected argument(s): {extra}"
    return None


def handle(message: dict):
    """Return a response dict, or None for notifications."""
    req_id = message.get("id")
    method = message.get("method", "")
    params = message.get("params") or {}
    if method == "initialize":
        return _result(req_id, {"protocolVersion": PROTOCOL_VERSION,
                                "capabilities": {"tools": {"listChanged": False}},
                                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": [
            {k: t[k] for k in ("name", "description", "inputSchema", "outputSchema") if k in t} for t in TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        tool = TOOL_INDEX.get(name)
        if tool is None:
            return _error(req_id, -32602, f"unknown tool: {name}")
        args = params.get("arguments") or {}
        problem = _validate_args(tool, args)
        if problem:
            return _error(req_id, -32602, f"INVALID_ARGUMENT: {problem}")
        try:
            out = TOOL_HANDLERS[name](args)
        except NotImplementedError as e:
            return _result(req_id, {"isError": True, "content": [{"type": "text", "text": f"NOT_IMPLEMENTED: {e}"}],
                                    "structuredContent": {"status": "error",
                                                          "error": {"code": "NOT_IMPLEMENTED", "message": str(e), "retryable": False},
                                                          "schema": {"inputSchema": tool.get("inputSchema"),
                                                                     "outputSchema": tool.get("outputSchema")}}})
        except Exception as e:  # noqa: BLE001 — never leak a stack trace to the model
            return _result(req_id, {"isError": True, "content": [{"type": "text", "text": "UPSTREAM_ERROR"}],
                                    "structuredContent": {"status": "error",
                                                          "error": {"code": "UPSTREAM_ERROR", "message": type(e).__name__, "retryable": True}}})
        return _result(req_id, {"content": [{"type": "text", "text": json.dumps(out)}], "structuredContent": out})
    if req_id is None:
        return None
    return _error(req_id, -32601, f"method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            sys.stdout.flush()
            continue
        response = handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
