"""Harness layers 4 (budget circuit breaker) and 5 (telemetry) — docs/HARNESS.md.

The model CLI is replaced by a small executable that prints Claude Code's real --output-format json shape, so the
wrapper's parsing, accounting and refusal paths run for real; the OTLP export goes to a real local HTTP server."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("deliver_h45", REPO / "scripts" / "deliver.py")
d = importlib.util.module_from_spec(spec)
sys.modules["deliver_h45"] = d
spec.loader.exec_module(d)
import telemetry  # noqa: E402


def fake_claude(tmp: Path, cost: float = 0.25, subtype: str = "success", text: str = "done") -> str:
    exe = tmp / "claude"
    reply = {"type": "result", "subtype": subtype, "is_error": subtype != "success", "result": text, "num_turns": 3,
             "total_cost_usd": cost, "usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 7}}
    exe.write_text(f"#!{sys.executable}\nimport sys, json\nopen({str(tmp / 'argv.json')!r}, 'w').write(json.dumps(sys.argv))\n"
                   f"print(json.dumps({reply!r}))\n", encoding="utf-8")
    exe.chmod(0o755)
    return str(exe)


class Args:
    builder, model, dry, provider = "claude-code", "claude-sonnet-5-5", True, "none"

    def __init__(self, budget=None):
        self.budget_usd = budget


def make_run(budget=None):
    r = d.Run({"name": "t", "stages": []}, Args(budget), Path("/nonexistent"))
    r.run_id = "r1"
    return r


def test_cost_tokens_and_a_span_are_recorded_and_the_reply_text_comes_back(tmp_path):
    run = make_run()
    out = run.run_claude([fake_claude(tmp_path), "-p", "x"], tmp_path, 30, "code")
    assert out.returncode == 0 and out.stdout == "done"
    assert run.record["llm"] == {"calls": 1, "cost_usd": 0.25, "input_tokens": 100, "output_tokens": 7}
    span = [s for s in run.tracer.spans if s.attrs.get("llm.call")][0]
    assert span.name == "llm code" and span.attrs["llm.cost_usd"] == 0.25 and span.attrs["llm.turns"] == 3
    assert run.tracer.totals()["cost_usd"] == 0.25


def test_each_call_gets_what_is_left_of_the_budget(tmp_path):
    run = make_run(budget=1.0)
    exe = fake_claude(tmp_path, cost=0.3)
    run.run_claude([exe, "-p", "x"], tmp_path, 30, "a")
    run.run_claude([exe, "-p", "y"], tmp_path, 30, "b")
    argv = json.loads((tmp_path / "argv.json").read_text())
    assert argv[argv.index("--max-budget-usd") + 1] == "0.7000"        # second call: 1.00 - 0.30


def test_a_run_over_budget_does_not_start_the_next_call(tmp_path):
    run = make_run(budget=0.5)
    exe = fake_claude(tmp_path, cost=0.6)
    run.run_claude([exe, "-p", "x"], tmp_path, 30, "a")
    with pytest.raises(d.StepError, match="budget exceeded: this run has spent \\$0.60 of its \\$0.50"):
        run.run_claude([exe, "-p", "y"], tmp_path, 30, "b")
    assert run.record["llm"]["calls"] == 1


def test_the_model_stopping_at_the_budget_is_a_budget_verdict_not_a_silent_success(tmp_path):
    run = make_run(budget=0.5)
    with pytest.raises(d.StepError, match="budget exceeded during code"):
        run.run_claude([fake_claude(tmp_path, cost=0.5, subtype="error_max_budget_usd"), "-p", "x"], tmp_path, 30, "code")


def test_a_cli_without_json_output_still_returns_its_text(tmp_path):
    exe = tmp_path / "claude"
    exe.write_text(f"#!{sys.executable}\nprint('plain reply')\n", encoding="utf-8")
    exe.chmod(0o755)
    out = make_run().run_claude([str(exe), "-p", "x"], tmp_path, 30, "x")
    assert out.stdout.strip() == "plain reply"


def test_spans_nest_and_the_trace_is_otlp_json(tmp_path):
    tr = telemetry.Tracer("deliver", "r1", pipeline="p")
    stage = tr.start("stage build")
    step = tr.start("step code", parent=stage)
    tr.record("llm code", 1, 2, parent=step, **{"llm.call": True, "llm.cost_usd": 0.1})
    tr.end(step, **{"step.status": "ok"})
    tr.end(stage, **{"gate.verdict": "pass"})
    tr.write(tmp_path / "trace.json")
    spans = json.loads((tmp_path / "trace.json").read_text())["resourceSpans"][0]["scopeSpans"][0]["spans"]
    by = {s["name"]: s for s in spans}
    assert by["step code"]["parentSpanId"] == by["stage build"]["spanId"]
    assert by["llm code"]["parentSpanId"] == by["step code"]["spanId"]
    assert len({s["traceId"] for s in spans}) == 1 and len(spans[0]["traceId"]) == 32 and len(spans[0]["spanId"]) == 16


EXPORT_CHECK = r"""
import http.server, json, sys, threading
sys.path.insert(0, sys.argv[1])
import telemetry
got = {}
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        got["path"], got["auth"] = self.path, self.headers.get("Authorization")
        got["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.handle_request, daemon=True).start()
tr = telemetry.Tracer("deliver", "r1")
with tr.span("stage build"):
    pass
res = tr.export(f"http://127.0.0.1:{srv.server_port}", "Authorization=Bearer t")
print(json.dumps({"res": res, "got": got, "dead": tr.export("http://127.0.0.1:9", ""), "none": tr.export("", "")}))
"""


def test_export_posts_otlp_to_the_configured_endpoint_and_never_raises(tmp_path):
    """Sockets are blocked in-process (conftest), so the server and the export run in a subprocess."""
    import subprocess
    r = subprocess.run([sys.executable, "-c", EXPORT_CHECK, str(REPO / "scripts")], capture_output=True, text=True, timeout=60)
    out = json.loads(r.stdout)
    assert out["res"].startswith("exported") and out["got"]["path"] == "/v1/traces" and out["got"]["auth"] == "Bearer t"
    assert out["got"]["body"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["name"] == "stage build"
    assert out["dead"].startswith("export failed") and out["none"] == "not configured"
