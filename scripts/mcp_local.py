#!/usr/bin/env python3
"""Local MCP server for the delivery pipelines — stdio, JSON-RPC 2.0, stdlib only, no portal, no network.

    python3 scripts/mcp_local.py            # speaks MCP on stdin/stdout; register it in the IDE (.mcp.json):
    {"mcpServers": {"skills-factory": {"command": "python3", "args": ["scripts/mcp_local.py"]}}}

The whole ADLC loop runs on the developer's machine or CI: every tool shells out to `scripts/deliver.py` (one code
path — the CLI, the MCP server and the optional portal mirror all drive the same executor), so what the IDE agent
does through this server is exactly what `deliver.py` does on the terminal, with the same evidence bundle,
registry.jsonl line and provenance.json. Runs live under $SF_RUNS_DIR (default runs/ under giri-skills).

Tools (docs/DELIVERY-PIPELINES.md → Local mode):
  deliver          start a run {pipeline, repo, request, brief?, ref?, builder?, model?, base_url?, provider?, dry?, …}
                   → run id, out dir, status and the first stop (approval / builder / input / wiring error)
  delivery_status  {run} — an out directory or a run id → stage table, the current stop, the resume command
  approve          {run, step, by, note?, resume?} — records the approval (source: mcp) and, by default, resumes the run
  reject           {run, step, by, note} — records the rejection; a resume stops with exit 3 until the step is approved again
  list_runs        {} — every run under the runs dir
  role_packet      {run} — the current stop's PROMPT.md (the role packet) so the IDE agent can act on it

Protocol: `initialize`, `notifications/initialized` (no reply), `ping`, `tools/list`, `tools/call`; newline-delimited
JSON-RPC 2.0 messages on stdin/stdout, logs on stderr. Unknown methods answer -32601, bad params -32602.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DELIVER = HERE / "deliver.py"
SERVER_INFO = {"name": "skills-factory-local", "version": "0.1.0"}
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
RPC_PARSE, RPC_INVALID_REQUEST, RPC_METHOD_NOT_FOUND, RPC_INVALID_PARAMS, RPC_INTERNAL = -32700, -32600, -32601, -32602, -32603
BUILDERS = ["none", "manual", "claude-code", "openai-compat"]
PROVIDERS = ["dry", "none", "anthropic", "openai"]
RUN_TIMEOUT_S = float(os.environ.get("SF_MCP_RUN_TIMEOUT", "0") or 0) or None   # a real run may take as long as it takes
EXIT_MEANING = {0: "every stage passed", 1: "a gate or step failed", 2: "bad arguments, missing input or pipeline wiring error",
                3: "waiting for an approval", 4: "waiting for the builder"}


def runs_dir() -> Path:
    return Path(os.environ.get("SF_RUNS_DIR") or (ROOT / "runs")).expanduser()


def pipelines() -> list[str]:
    names = sorted(p.stem for p in (ROOT / "pipelines").glob("*.json"))
    names += sorted(f"{p.stem}" for p in (ROOT / "pipelines" / "composed").glob("*.json") if p.stem not in names)
    return names


RUN_PARAM = {"type": "string", "description": "The run's out directory, or its run id (as `deliver` / `list_runs` report it)."}


def tools() -> list[dict]:
    names = pipelines()
    return [
        {"name": "deliver", "title": "Deliver through a pipeline (local)",
         "description": "Start a delivery run on this machine: a request through a pipeline template on a repository, stage by stage, each owned by a "
                        "role and gated — no portal, no network. Returns the run id, the out directory, the status and the first stop (an approval to "
                        "give with `approve`, or a role stop whose packet `role_packet` returns). Evidence lands in <out>/evidence/.\n"
                        + "\n".join(f"- {n}" for n in names),
         "inputSchema": {"type": "object", "properties": {
             "pipeline": {"type": "string", "description": "Pipeline template name (pipelines/<name>.json or pipelines/composed/<name>.json) or a path.", **({"enum": names} if names else {})},
             "repo": {"type": "string", "description": "A local checkout path (or owner/name to clone with gh, or the directory to create for greenfield)."},
             "request": {"type": "string", "description": "What to deliver, in the requester's words."},
             "brief": {"type": "string", "description": "Path to a product brief JSON (optional)."},
             "ref": {"type": "string", "description": "Branch or commit to start from."},
             "builder": {"type": "string", "enum": BUILDERS, "description": "Who fills the role stops (default none: the IDE agent does, from the role packet)."},
             "model": {"type": "string", "description": "openai-compat builder: the model name."},
             "base_url": {"type": "string", "description": "openai-compat builder: the endpoint base URL (e.g. http://localhost:11434/v1)."},
             "provider": {"type": "string", "enum": PROVIDERS, "description": "Model provider for the skills' model steps (default dry)."},
             "dry": {"type": "boolean", "description": "Work on a copy of the repo under <out>/repo; the pr step opens nothing (default false)."},
             "approve_all": {"type": "boolean", "description": "Satisfy every approval step up front (the caller approves)."},
             "no_baseline": {"type": "boolean", "description": "Skip the pre-change baseline (every lint finding is then new)."},
             "install": {"type": "string", "description": "Code step: auto|none|<cmd> (default auto)."},
             "tests": {"type": "string", "description": "Code step: auto|none|<cmd> (default auto)."},
             "inputs": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Any other pipeline input (name=value), e.g. {\"name\": \"my-app\"} for greenfield."},
             "run_id": {"type": "string", "description": "Run id (default: derived from pipeline + request + repo, with a time suffix unless dry)."},
             "out": {"type": "string", "description": "Run directory (default: <runs dir>/<run id>)."},
         }, "required": ["pipeline", "repo", "request"], "additionalProperties": False},
         "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}},
        {"name": "delivery_status", "title": "Delivery run status (local)",
         "description": "Status, current stage, per-stage gate verdicts, the current stop (needs_approval / needs_builder / needs_input / wiring_error / "
                        "rejected, with its contents) and the resume command of a run on this machine.",
         "inputSchema": {"type": "object", "properties": {"run": RUN_PARAM}, "required": ["run"], "additionalProperties": False},
         "annotations": {"readOnlyHint": True, "openWorldHint": False}},
        {"name": "approve", "title": "Approve a step",
         "description": "Record an approval of a step in <out>/approvals.json (source: mcp) and, unless resume is false, resume the run — the reply is the "
                        "run's status after the resume (the stage passed, or the next stop).",
         "inputSchema": {"type": "object", "properties": {"run": RUN_PARAM, "step": {"type": "string", "description": "The approval step id (needs_approval.json `step`)."},
                                                           "by": {"type": "string", "description": "Who approves."}, "note": {"type": "string"},
                                                           "resume": {"type": "boolean", "description": "Resume the run after recording the approval (default true)."}},
                         "required": ["run", "step", "by"], "additionalProperties": False},
         "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
        {"name": "reject", "title": "Reject a step",
         "description": "Record a rejection in <out>/rejections.json and mark the run rejected: a resume stops with exit 3 and the note until the step is approved again.",
         "inputSchema": {"type": "object", "properties": {"run": RUN_PARAM, "step": {"type": "string"}, "by": {"type": "string"}, "note": {"type": "string", "description": "Why — shown on every resume until a new approval."}},
                         "required": ["run", "step", "by", "note"], "additionalProperties": False},
         "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
        {"name": "list_runs", "title": "List delivery runs (local)",
         "description": "Every delivery run under the runs dir ($SF_RUNS_DIR, else runs/): run id, pipeline, repo, status, stage, started, out dir.",
         "inputSchema": {"type": "object", "properties": {"runs_dir": {"type": "string", "description": "Runs directory (default: $SF_RUNS_DIR or runs/)."}}, "additionalProperties": False},
         "annotations": {"readOnlyHint": True, "openWorldHint": False}},
        {"name": "role_packet", "title": "The current stop's role packet",
         "description": "The PROMPT.md of the run's current builder stop (product manager, architect, files, code): a self-contained packet — what to produce, "
                        "where, the gate checks, every input inlined, the role's skill and the resume command. Act on it, write the outputs at the expected "
                        "paths, then resume (the packet ends with the command). A run waiting for an approval returns what is under review instead.",
         "inputSchema": {"type": "object", "properties": {"run": RUN_PARAM}, "required": ["run"], "additionalProperties": False},
         "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    ]


# ------------------------------------------------------------------ deliver.py, one code path

class ToolError(Exception):
    pass


def deliver_py(*argv: str, cwd: Path | None = None, timeout: float | None = 600) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(DELIVER), *argv], capture_output=True, text=True, cwd=str(cwd or ROOT), timeout=timeout)


def deliver_json(*argv: str) -> dict:
    r = deliver_py(*argv)
    if r.returncode != 0:
        raise ToolError((r.stderr or r.stdout).strip()[:1500] or f"deliver.py {argv[0]} exited {r.returncode}")
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise ToolError(f"deliver.py {argv[0]} returned no JSON: {r.stdout[:300]!r}") from None


def status_of(run: str) -> dict:
    return deliver_json("status", run, "--json")


def render_status(d: dict, head: str = "") -> str:
    lines = [head or f"Delivery run {d['run_id']} — {d['status']}" + (f" · at {d['stage']}" if d.get("stage") else "") + (" · DRY" if d.get("dry") else ""),
             f"Out: {d['out']}"]
    for s in d.get("stages") or []:
        g = s.get("gate") or {}
        lines.append(f"- {s['id']} ({s.get('role', '?')}): {s['status']}" + (f" · gate {g['verdict']}" if g.get("verdict") else "") + (f" — {g['detail'][:160]}" if g.get("detail") else ""))
    stop = d.get("stop") or {"kind": "none"}
    k = stop.get("kind")
    if k == "needs_approval":
        lines.append(f"Waiting for approval of step '{stop.get('step')}' ({stop.get('role')}): {stop.get('note', '')} — call approve {{run, step: '{stop.get('step')}', by}}; under review: "
                     + ", ".join(stop.get("review") or []))
    elif k == "needs_builder":
        lines.append(f"Waiting for the {stop.get('role') or 'builder'} at step '{stop.get('step')}': {stop.get('why', '')} — call role_packet for the packet, write the outputs, then resume.")
    elif k == "needs_input":
        lines.append("Needs input: " + ", ".join(f"{m.get('name')} ({m.get('from', '')})" for m in stop.get("missing") or []))
    elif k == "wiring_error":
        lines.append(f"Pipeline wiring error: {stop.get('message', '')}")
    elif k == "rejected":
        r = stop.get("rejection") or {}
        lines.append(f"Rejected at step '{r.get('step')}' by {r.get('by')}: {r.get('note', '')} — approve the step again to continue.")
    elif d.get("status") == "passed":
        lines.append(f"Every stage passed — evidence: {d.get('evidence')}")
    lines.append(f"Resume: {d.get('resume_command', '')}")
    return "\n".join(lines)


def resume(d: dict) -> subprocess.CompletedProcess:
    argv = [a for a in (d.get("argv") or []) if a != "--resume"]
    if not argv:
        raise ToolError("the run records no command line to resume (run.json `argv`)")
    cwd = Path(d.get("cwd") or ROOT)
    return deliver_py(*argv, "--resume", cwd=cwd if cwd.is_dir() else ROOT, timeout=RUN_TIMEOUT_S)


def result(text: str, structured: dict, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "structuredContent": structured, **({"isError": True} if is_error else {})}


def need(a: dict, *keys: str) -> None:
    missing = [k for k in keys if not (isinstance(a.get(k), str) and a[k].strip())]
    if missing:
        raise InvalidParams(f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} required")


class InvalidParams(Exception):
    pass


def tool_deliver(a: dict) -> dict:
    need(a, "pipeline", "repo", "request")
    dry = bool(a.get("dry"))
    base = hashlib.sha256(f"{a['pipeline']}|{a['request']}|{Path(a['repo']).expanduser()}".encode()).hexdigest()[:10]
    run_id = str(a.get("run_id") or "").strip() or (base if dry else f"{base}-{int(time.time())}")
    out = Path(str(a.get("out") or "").strip() or (runs_dir() / run_id)).expanduser()
    argv = [a["pipeline"], "--repo", a["repo"], "--request", a["request"], "--out", str(out), "--run-id", run_id,
            "--builder", str(a.get("builder") or "none"), "--provider", str(a.get("provider") or "dry")]
    for key, flag in (("brief", "--brief"), ("ref", "--ref"), ("model", "--model"), ("base_url", "--base-url"), ("install", "--install"), ("tests", "--tests")):
        if a.get(key):
            argv += [flag, str(a[key])]
    for k, v in (a.get("inputs") or {}).items():
        argv += ["--input", f"{k}={v}"]
    if dry:
        argv.append("--dry")
    if a.get("approve_all"):
        argv.append("--approve-all")
    if a.get("no_baseline"):
        argv.append("--no-baseline")
    r = deliver_py(*argv, timeout=RUN_TIMEOUT_S)
    if not (out / "run.json").is_file():
        return result(f"deliver.py exited {r.returncode} before the run started:\n{(r.stderr or r.stdout).strip()[:2000]}",
                      {"run_id": run_id, "out": str(out), "exit": r.returncode, "stderr": r.stderr[-2000:], "stdout": r.stdout[-2000:]}, is_error=True)
    d = status_of(str(out))
    d["exit"], d["exit_meaning"] = r.returncode, EXIT_MEANING.get(r.returncode, "")
    return result(render_status(d, f"Delivery run {d['run_id']} — {d['status']} (exit {r.returncode}: {d['exit_meaning']})"), d, is_error=r.returncode in (1, 2))


def tool_delivery_status(a: dict) -> dict:
    need(a, "run")
    d = status_of(a["run"])
    return result(render_status(d), d)


def tool_approve(a: dict) -> dict:
    need(a, "run", "step", "by")
    rec = deliver_json("approve", a["run"], "--step", a["step"], "--by", a["by"], "--note", str(a.get("note") or ""), "--source", "mcp", "--json")
    if a.get("resume") is False:
        d = status_of(rec["out"])
        d["approval"] = rec["approval"]
        return result(f"Approved step '{a['step']}' by {a['by']} — recorded in {rec['file']}; not resumed.\nResume: {rec['resume_command']}", d)
    d0 = status_of(rec["out"])
    r = resume(d0)
    d = status_of(rec["out"])
    d["approval"], d["exit"], d["exit_meaning"] = rec["approval"], r.returncode, EXIT_MEANING.get(r.returncode, "")
    return result(render_status(d, f"Approved step '{a['step']}' by {a['by']}; resumed — run {d['run_id']} {d['status']} (exit {r.returncode}: {d['exit_meaning']})"),
                  d, is_error=r.returncode in (1, 2))


def tool_reject(a: dict) -> dict:
    need(a, "run", "step", "by", "note")
    rec = deliver_json("reject", a["run"], "--step", a["step"], "--by", a["by"], "--note", a["note"], "--source", "mcp", "--json")
    d = status_of(rec["out"])
    d["rejection"] = rec["rejection"]
    return result(f"Rejected step '{a['step']}' by {a['by']}: {a['note']} — recorded in {rec['file']}. The run is marked rejected; a resume stops "
                  f"with exit 3 until the step is approved again (approve {{run, step: '{a['step']}', by}}).", d)


def tool_list_runs(a: dict) -> dict:
    argv = ["list", "--json"] + (["--runs", str(a["runs_dir"])] if a.get("runs_dir") else [])
    d = deliver_json(*argv)
    rows = d.get("runs") or []
    text = (f"{len(rows)} delivery run(s) under {d.get('runs_dir')}:\n" + "\n".join(
        f"- {r['run_id']} · {r['pipeline']} · {r['repo']} · {r['status']}" + (f" at {r['stage']}" if r.get("stage") else "") + f" · started {r['started']} · {r['out']}" for r in rows)
            if rows else f"no delivery runs under {d.get('runs_dir')}")
    return result(text, d)


def tool_role_packet(a: dict) -> dict:
    need(a, "run")
    d = status_of(a["run"])
    stop = d.get("stop") or {"kind": "none"}
    if stop.get("kind") == "needs_builder":
        prompt = Path(str(stop.get("prompt") or ""))
        if not prompt.is_file():
            return result(f"the run stopped at step '{stop.get('step')}' but its packet is missing: {prompt}", {"run_id": d["run_id"], "stop": stop}, is_error=True)
        text = prompt.read_text(encoding="utf-8")
        return result(text, {"run_id": d["run_id"], "out": d["out"], "step": stop.get("step"), "role": stop.get("role") or "builder",
                             "expected": stop.get("expected"), "alternative": stop.get("alternative"), "prompt": str(prompt), "packet": text,
                             "resume_command": d.get("resume_command", "")})
    if stop.get("kind") == "needs_approval":
        return result(f"No role packet: run {d['run_id']} waits for approval of step '{stop.get('step')}' ({stop.get('role')}): {stop.get('note', '')}\n"
                      "Under review:\n" + "\n".join(f"- {Path(d['out']) / p}" for p in stop.get("review") or []) + f"\nApprove with approve {{run, step: '{stop.get('step')}', by}}.",
                      {"run_id": d["run_id"], "out": d["out"], "stop": stop})
    if stop.get("kind") == "rejected":
        r = stop.get("rejection") or {}
        return result(f"No role packet: run {d['run_id']} is rejected at step '{r.get('step')}' by {r.get('by')}: {r.get('note', '')} — approve it again to continue.",
                      {"run_id": d["run_id"], "out": d["out"], "stop": stop})
    return result(f"No role packet: run {d['run_id']} is {d['status']}" + (f" ({stop.get('kind')})" if stop.get("kind") != "none" else "") + " — nothing waits for a role.",
                  {"run_id": d["run_id"], "out": d["out"], "stop": stop, "status": d["status"]})


TOOL_FNS = {"deliver": tool_deliver, "delivery_status": tool_delivery_status, "approve": tool_approve, "reject": tool_reject,
            "list_runs": tool_list_runs, "role_packet": tool_role_packet}


# ------------------------------------------------------------------ JSON-RPC over stdio

def ok(mid, res: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def fail(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle(msg) -> dict | None:
    if not isinstance(msg, dict):
        return fail(None, RPC_INVALID_REQUEST, "expected a JSON-RPC 2.0 object")
    mid = msg.get("id")
    method = msg.get("method")
    if msg.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return fail(mid, RPC_INVALID_REQUEST, 'expected jsonrpc "2.0" and a method')
    if "id" not in msg or mid is None:
        return None   # a notification (notifications/initialized, cancelled, …): no reply
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    try:
        if method == "initialize":
            asked = str(params.get("protocolVersion") or "")
            return ok(mid, {"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                            "capabilities": {"tools": {"listChanged": False}}, "serverInfo": SERVER_INFO,
                            "instructions": "Skills Factory — local delivery pipelines (no portal). `deliver` starts a run on this machine and stops at "
                                            "the first approval or role stop; `role_packet` gives you the packet to act on (write the outputs at the paths it "
                                            "names, then resume with the command it ends with); `approve` records an approval and resumes; `delivery_status` "
                                            "and `list_runs` read the local registry. Evidence and provenance land under the run's out directory."})
        if method == "ping":
            return ok(mid, {})
        if method == "tools/list":
            return ok(mid, {"tools": tools()})
        if method == "tools/call":
            name = str(params.get("name") or "")
            args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            fn = TOOL_FNS.get(name)
            if fn is None:
                return fail(mid, RPC_INVALID_PARAMS, f"unknown tool: {name} (one of {', '.join(TOOL_FNS)})")
            try:
                return ok(mid, fn(args))
            except InvalidParams as e:
                return fail(mid, RPC_INVALID_PARAMS, str(e))
            except ToolError as e:
                return ok(mid, result(str(e), {"error": str(e)}, is_error=True))
            except subprocess.TimeoutExpired as e:
                return ok(mid, result(f"deliver.py timed out after {e.timeout}s", {"error": "timeout"}, is_error=True))
        return fail(mid, RPC_METHOD_NOT_FOUND, f"method not found: {method}")
    except Exception as e:   # never let one request kill the server
        return fail(mid, RPC_INTERNAL, f"{type(e).__name__}: {e}")


def serve(stdin=None, stdout=None) -> int:
    inp = stdin or sys.stdin.buffer
    outp = stdout or sys.stdout.buffer
    for raw in inp:
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp = fail(None, RPC_PARSE, "parse error")
        else:
            resp = handle(msg)
        if resp is not None:
            outp.write((json.dumps(resp) + "\n").encode("utf-8"))
            outp.flush()
    return 0


if __name__ == "__main__":
    sys.exit(serve())
