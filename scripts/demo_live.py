#!/usr/bin/env python3
"""Live demo: call a published skill the way Claude, Cursor or an app does — over MCP and over the REST API.

    python3 scripts/demo_live.py                      # prompts for the key (hidden); production portal
    SF_HOST=https://<host> python3 scripts/demo_live.py

The key is a workspace API key (Administration → API keys, starts sf_live_). It is read from $SF_KEY or typed
hidden; it is never printed or written anywhere. Every number shown comes from the live server's response.
Standard library only.
"""
from __future__ import annotations

import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOST = os.environ.get("SF_HOST", "https://giri-skills-studio.vercel.app").rstrip("/")
SKILL = "llm-cost-model"
FIXTURES = Path(__file__).resolve().parents[1] / "skills/ai-platform/llm-cost-model/evals/fixtures"
TASK = "Estimate what our LLM features will cost per month and where we could save"

B, D, G, R, X = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[0m"
if not sys.stdout.isatty():
    B = D = G = R = X = ""


def step(n: int, title: str, what: str) -> None:
    print(f"\n{B}{n}. {title}{X}\n{D}{what}{X}")


def call(key: str, method: str, path: str, body: dict | None = None, timeout: int = 90) -> tuple[int, dict, float]:
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json, text/event-stream"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["MCP-Protocol-Version"] = "2025-06-18"
        data = json.dumps(body).encode()
    req = urllib.request.Request(HOST + path, data=data, method=method, headers=headers)
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}"), time.monotonic() - t
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}"), time.monotonic() - t
        except ValueError:
            return e.code, {}, time.monotonic() - t


def rpc(key: str, mid: int, method: str, params: dict | None = None) -> tuple[dict, float]:
    status, body, secs = call(key, "POST", "/api/mcp", {"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
    if status >= 400 or "error" in body:
        err = body.get("error", {})
        sys.exit(f"{R}MCP {method} failed ({status}): {err.get('message', body)}{X}")
    return body["result"], secs


def main() -> None:
    key = os.environ.get("SF_KEY") or getpass.getpass("Workspace API key (sf_live_…, hidden): ").strip()
    if not key.startswith("sf_live_"):
        sys.exit(f"{R}That is not a workspace key (they start sf_live_). Create one in Administration → API keys.{X}")
    print(f"{B}Skills Factory — live demo{X}  {D}{HOST}{X}")

    step(1, "Connect, as Claude or Cursor does", "MCP initialize: the client learns who the server is and how to use it.")
    r, s = rpc(key, 1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "demo_live.py", "version": "1"}})
    print(f"   Server: {G}{r['serverInfo']['name']}{X} · protocol {r['protocolVersion']} · {s:.1f}s")

    step(2, "Discover the tools", "MCP tools/list: every published skill is a tool with its input contract.")
    r, s = rpc(key, 2, "tools/list")
    names = [t["name"] for t in r["tools"]]
    skills = [n for n in names if n not in ("find_skill", "get_run")]
    print(f"   {G}{len(skills)} published skills{X} as tools (+ find_skill, get_run) · {s:.1f}s")
    print(f"   {D}{', '.join(sorted(skills))}{X}")

    step(3, "Ask in plain words", f'find_skill: "{TASK}"')
    r, s = rpc(key, 3, "tools/call", {"name": "find_skill", "arguments": {"task": TASK}})
    hits = r.get("structuredContent", {}).get("hits", [])
    for h in hits[:3]:
        tool = f"→ tool {G}{h['tool']}{X}" if h.get("tool") else f"{D}(not published here){X}"
        print(f"   {h.get('skill')} {tool}\n     {D}{h.get('produces', '')}{X}")
    print(f"   {D}{s:.1f}s{X}")

    step(4, "Run it on real inputs", f"tools/call {SKILL}: workload, price sheet and model assignment (sample files, labelled fictional).")
    args = {n: (FIXTURES / f"{n}.csv").read_text(encoding="utf-8") for n in ("workload", "prices", "assignment")}
    args["budget_usd_month"] = "1000"
    r, s = rpc(key, 4, "tools/call", {"name": SKILL, "arguments": args})
    sc = r.get("structuredContent", {})
    checks = sc.get("checks") or []
    print(f"   Run {sc.get('run_id', '?')}: {G if sc.get('status') == 'succeeded' else R}{sc.get('status')}{X}"
          f" · {sum(1 for c in checks if c.get('pass'))}/{len(checks)} output checks passed · {s:.1f}s")
    text = "\n".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
    print("   " + "\n   ".join(text.splitlines()[:40]))

    step(5, "Same skill from any app", "REST: GET /api/v1/runs/{id} — the run is recorded once, readable by API and audited.")
    status, body, s = call(key, "GET", f"/api/v1/runs/{sc.get('run_id')}")
    extra = " · ".join(f"{k} {body[k]}" for k in ("skill", "version", "source", "duration_ms") if body.get(k) is not None)
    print(f"   HTTP {status} · status {body.get('status')}{' · ' + extra if extra else ''} · {s:.1f}s")
    print(f"\n{B}Done.{X} {D}Every value above came from the live server. The run is in the portal under Skills → Runs.{X}")


if __name__ == "__main__":
    main()
