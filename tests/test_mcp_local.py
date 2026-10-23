"""scripts/mcp_local.py — the local MCP server over stdio: initialize, tools/list, and the six tools driving a dry
delivery run on the fixture repo through scripts/deliver.py (no portal, no network, deterministic)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

SERVER = REPO_ROOT / "scripts" / "mcp_local.py"
FIX = REPO_ROOT / "tests" / "fixtures"
REPO = FIX / "delivery-repo"
BRIEF = FIX / "delivery-build" / "brief.json"
PATCH = FIX / "delivery-build" / "diff.patch"
REQUEST = "Export orders as CSV"
TOOLS = ["deliver", "delivery_status", "approve", "reject", "list_runs", "role_packet"]


class Client:
    """A minimal MCP stdio client: one JSON-RPC line out, one line back."""

    def __init__(self, runs_dir: Path):
        env = {**os.environ, "SF_RUNS_DIR": str(runs_dir)}
        self.p = subprocess.Popen([sys.executable, "-I", str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, env=env, cwd=str(REPO_ROOT))
        self.n = 0

    def send(self, msg: dict) -> None:
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()

    def call(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        self.send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})
        line = self.p.stdout.readline()
        assert line, "the server closed its stdout: " + self.p.stderr.read()
        resp = json.loads(line)
        assert resp["jsonrpc"] == "2.0" and resp["id"] == self.n
        return resp

    def tool(self, name: str, **arguments) -> dict:
        resp = self.call("tools/call", {"name": name, "arguments": arguments})
        assert "result" in resp, resp
        return resp["result"]

    def close(self) -> tuple[int, str]:
        self.p.stdin.close()
        code = self.p.wait(timeout=30)
        return code, self.p.stderr.read()


@pytest.fixture()
def client(tmp_path):
    c = Client(tmp_path / "runs")
    init = c.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}})
    assert init["result"]["protocolVersion"] == "2025-06-18" and init["result"]["serverInfo"]["name"] == "skills-factory-local"
    assert init["result"]["capabilities"] == {"tools": {"listChanged": False}} and "role_packet" in init["result"]["instructions"]
    c.send({"jsonrpc": "2.0", "method": "notifications/initialized"})          # a notification: no reply
    assert c.call("ping")["result"] == {}                                        # …and the next request is answered in order
    yield c
    code, err = c.close()
    assert code == 0, err


def text_of(res: dict) -> str:
    return res["content"][0]["text"]


def test_tools_list_has_the_six_tools_with_schemas(client):
    tools = client.call("tools/list")["result"]["tools"]
    assert [t["name"] for t in tools] == TOOLS
    by = {t["name"]: t for t in tools}
    assert by["deliver"]["inputSchema"]["required"] == ["pipeline", "repo", "request"]
    assert "feature-delivery" in by["deliver"]["inputSchema"]["properties"]["pipeline"]["enum"]
    assert by["deliver"]["inputSchema"]["properties"]["builder"]["enum"] == ["none", "manual", "claude-code", "openai-compat"]
    assert by["approve"]["inputSchema"]["required"] == ["run", "step", "by"] and by["reject"]["inputSchema"]["required"] == ["run", "step", "by", "note"]
    assert by["delivery_status"]["inputSchema"]["required"] == ["run"] and by["role_packet"]["inputSchema"]["required"] == ["run"]
    assert by["list_runs"]["annotations"]["readOnlyHint"] is True and by["deliver"]["annotations"]["openWorldHint"] is False
    for t in tools:
        assert t["inputSchema"]["type"] == "object" and t["inputSchema"]["additionalProperties"] is False and t["description"]


def test_unknown_method_and_tool_and_bad_params_are_json_rpc_errors(client):
    assert client.call("nope")["error"]["code"] == -32601
    assert client.call("tools/call", {"name": "nope", "arguments": {}})["error"]["code"] == -32602
    e = client.call("tools/call", {"name": "approve", "arguments": {"run": "x"}})["error"]
    assert e["code"] == -32602 and "step, by are required" in e["message"]
    client.p.stdin.write("not json\n"); client.p.stdin.flush()
    assert json.loads(client.p.stdout.readline())["error"]["code"] == -32700
    res = client.tool("delivery_status", run="no-such-run")
    assert res["isError"] is True and "no run found" in text_of(res)


def test_deliver_stops_at_the_approval_then_role_packet_approve_and_status_drive_the_loop(client, tmp_path):
    runs = tmp_path / "runs"
    res = client.tool("deliver", pipeline="feature-delivery", repo=str(REPO), request=REQUEST, brief=str(BRIEF), dry=True)
    assert "isError" not in res, text_of(res)
    d = res["structuredContent"]
    assert d["exit"] == 3 and d["status"] == "awaiting_approval" and d["stage"] == "architecture" and d["dry"] is True
    assert d["out"] == str(runs / d["run_id"]) and (runs / d["run_id"] / "run.json").is_file()
    assert d["stop"]["kind"] == "needs_approval" and d["stop"]["step"] == "plan-approval"
    assert [(s["id"], s["status"]) for s in d["stages"]] == [("requirements", "passed"), ("architecture", "awaiting_approval")]
    assert "waiting for an approval" in text_of(res) and "call approve" in text_of(res) and "Resume:" in text_of(res)
    assert d["run_id"] == "4abf5788d4" or len(d["run_id"]) == 10                              # dry: derived from pipeline + request + repo
    # the same run id → status by id or by out dir
    assert client.tool("delivery_status", run=d["run_id"])["structuredContent"]["out"] == d["out"]
    assert client.tool("delivery_status", run=d["out"])["structuredContent"]["stop"]["kind"] == "needs_approval"
    # no builder stop yet: role_packet says what waits for approval
    rp = client.tool("role_packet", run=d["run_id"])
    assert "waits for approval of step 'plan-approval'" in text_of(rp) and "plan-refine/tasks.csv" in text_of(rp)
    # approve → recorded with source mcp → resumed → the architecture stage passed, the build stage stops for the builder
    ap = client.tool("approve", run=d["run_id"], step="plan-approval", by="giri", note="plan ok")
    assert "isError" not in ap, text_of(ap)
    a = ap["structuredContent"]
    assert a["approval"] == {**a["approval"], "step": "plan-approval", "by": "giri", "note": "plan ok", "source": "mcp"}
    assert a["exit"] == 4 and a["status"] == "awaiting_builder" and a["stage"] == "build"
    assert {s["id"]: s["status"] for s in a["stages"]} == {"requirements": "passed", "architecture": "passed", "build": "awaiting_builder"}
    assert "Approved step 'plan-approval' by giri; resumed" in text_of(ap) and "call role_packet" in text_of(ap)
    aj = json.loads((runs / d["run_id"] / "evidence" / "02-architecture" / "plan-approval" / "approval.json").read_text())
    assert aj["by"] == "giri" and aj["source"] == "mcp"
    st = client.tool("delivery_status", run=d["run_id"])["structuredContent"]
    assert next(s for s in st["stages"] if s["id"] == "architecture")["status"] == "passed" and st["stop"]["step"] == "code"
    # the role packet is the code step's PROMPT.md
    rp = client.tool("role_packet", run=d["run_id"])
    assert "isError" not in rp
    assert text_of(rp).startswith("# Role: builder — step code (run ") and "## When done" in text_of(rp) and text_of(rp).rstrip().endswith("```")
    assert rp["structuredContent"]["step"] == "code" and rp["structuredContent"]["expected"] == str(runs / d["run_id"] / "build" / "diff.patch")
    assert text_of(rp) == Path(rp["structuredContent"]["prompt"]).read_text()
    prov = json.loads((runs / d["run_id"] / "evidence" / "provenance.json").read_text())
    assert prov["approvals"] == [{**prov["approvals"][0], "step": "plan-approval", "by": "giri", "source": "mcp"}]
    # list_runs sees it; the IDE agent drops the diff and the approve-less resume is left to the packet's command
    lr = client.tool("list_runs")
    assert lr["structuredContent"]["runs"][0]["run_id"] == d["run_id"] and "awaiting_builder at build" in text_of(lr)
    lines = [json.loads(ln) for ln in (runs / "registry.jsonl").read_text().splitlines()]
    assert [e["status"] for e in lines] == ["running", "passed", "awaiting_approval", "approved", "running", "passed", "awaiting_builder"]


def test_reject_marks_the_run_and_approve_without_resume_only_records(client, tmp_path):
    runs = tmp_path / "runs"
    d = client.tool("deliver", pipeline="feature-delivery", repo=str(REPO), request=REQUEST, brief=str(BRIEF), dry=True)["structuredContent"]
    rj = client.tool("reject", run=d["out"], step="plan-approval", by="lead", note="no rollback on T2")
    assert "isError" not in rj and rj["structuredContent"]["rejection"]["source"] == "mcp" and rj["structuredContent"]["status"] == "rejected"
    assert "marked rejected" in text_of(rj)
    st = client.tool("delivery_status", run=d["run_id"])["structuredContent"]
    assert st["stop"]["kind"] == "rejected" and st["stop"]["rejection"]["note"] == "no rollback on T2"
    assert "is rejected at step 'plan-approval'" in text_of(client.tool("role_packet", run=d["run_id"]))
    ap = client.tool("approve", run=d["run_id"], step="plan-approval", by="giri", resume=False)
    assert "not resumed" in text_of(ap) and ap["structuredContent"]["status"] == "rejected"                   # nothing ran
    ap = client.tool("approve", run=d["run_id"], step="plan-approval", by="giri", note="rollback added")
    assert ap["structuredContent"]["status"] == "awaiting_builder" and ap["structuredContent"]["exit"] == 4
    assert [x["by"] for x in json.loads((runs / d["run_id"] / "approvals.json").read_text())["approvals"]] == ["giri"]  # one approval per step
    assert [e["status"] for e in (json.loads(ln) for ln in (runs / "registry.jsonl").read_text().splitlines())].count("rejected") == 1


def test_deliver_with_a_manual_patch_and_approve_all_runs_every_stage(client, tmp_path):
    runs = tmp_path / "runs"
    res = client.tool("deliver", pipeline="feature-delivery", repo=str(REPO), request=REQUEST, brief=str(BRIEF), dry=True,
                      builder="manual", approve_all=True, inputs={}, run_id="mcp-happy")
    # --patch is a CLI-only convenience: the IDE drops the diff at <out>/build/diff.patch; the first stop is the code step
    d = res["structuredContent"]
    assert d["exit"] == 4 and d["run_id"] == "mcp-happy" and d["stop"]["kind"] == "needs_builder"
    (runs / "mcp-happy" / "build").mkdir(parents=True, exist_ok=True)
    (runs / "mcp-happy" / "build" / "diff.patch").write_bytes(PATCH.read_bytes())
    r = subprocess.run([sys.executable, "-I", str(REPO_ROOT / "scripts" / "deliver.py"), *d["argv"], "--resume"],
                       capture_output=True, text=True, cwd=d["cwd"], env={**os.environ, "SF_RUNS_DIR": str(runs)})
    assert r.returncode == 0, r.stdout + r.stderr
    st = client.tool("delivery_status", run="mcp-happy")["structuredContent"]
    assert st["status"] == "passed" and st["stop"]["kind"] == "none" and all(s["status"] == "passed" for s in st["stages"])
    assert "Every stage passed" in text_of(client.tool("delivery_status", run="mcp-happy"))
    assert "nothing waits for a role" in text_of(client.tool("role_packet", run="mcp-happy"))


def test_deliver_that_cannot_start_is_a_tool_error_not_a_crash(client, tmp_path):
    res = client.tool("deliver", pipeline="no-such-pipeline", repo=str(REPO), request=REQUEST, dry=True)
    assert res["isError"] is True and "pipeline not found" in text_of(res)
    e = client.call("tools/call", {"name": "deliver", "arguments": {"pipeline": "feature-delivery"}})["error"]
    assert e["code"] == -32602 and "repo, request are required" in e["message"]
    assert client.tool("list_runs")["structuredContent"]["runs"] == []
