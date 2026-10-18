"""Offline tests for the Skills Factory runtime (studio/api/py/run.py).

Run from studio/:  python3 -m pytest tests/test_factory_runtime.py -q
Needs api/py/bundle.json (npm run ingest). No network: provider "none" only; the anthropic path is tested
with the HTTP call monkeypatched (what the callback does with a provider reply, never a real call).
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path

import pytest

STUDIO = Path(__file__).resolve().parents[1]
RUN_PY = STUDIO / "api" / "py" / "run.py"
BUNDLE = STUDIO / "api" / "py" / "bundle.json"

pytestmark = pytest.mark.skipif(not BUNDLE.is_file(), reason="api/py/bundle.json missing — run `npm run ingest` in studio/")


@pytest.fixture(scope="module")
def rt(tmp_path_factory):
    os.environ["SF_WORK_ROOT"] = str(tmp_path_factory.mktemp("sfwork"))
    spec = importlib.util.spec_from_file_location("sf_run", RUN_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.WORK_ROOT = Path(os.environ["SF_WORK_ROOT"])
    return mod


def _fixture_text(rt, repo_skill: str, rel: str) -> str:
    return rt.load_bundle()[f"skills/{repo_skill}/{rel}"]


def test_repo_skill_runs_end_to_end_without_a_model(rt, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    wbs = _fixture_text(rt, "presales/effort-estimator", "evals/fixtures/wbs.csv")
    rates = _fixture_text(rt, "presales/effort-estimator", "evals/fixtures/rates.csv")
    res = rt.execute({
        "run_id": "t-repo-1", "skill": {"kind": "repo", "repo_skill": "presales/effort-estimator"},
        "inputs": {"wbs": {"kind": "text", "content": wbs, "ext": "csv"}, "rates": {"kind": "text", "content": rates, "ext": "csv"},
                   "client": {"kind": "value", "value": "Acme"}},
        "provider": "anthropic", "model": "claude-sonnet-4-5", "timeout_s": 50,
    })
    assert res["exit_code"] == 1, res["error"]          # llm step skipped -> its checks fail honestly
    assert res["status"] == "failed"
    assert res["provider"] == {"requested": "anthropic", "used": "none", "available": False,
                               "note": "provider unavailable — set ANTHROPIC_API_KEY on the server; llm steps were skipped"}
    rj = res["run_json"]
    steps = {s["step"]: s for s in rj["steps"]}
    assert steps["model-json"]["ok"] and steps["model-report"]["ok"]
    assert steps["memo"]["skipped"] and steps["memo"]["skipped_reason"] == "no provider key (LLM step not run)"
    paths = {o["path"] for o in res["outputs"]}
    assert {"estimate.json", "estimate.md"} <= paths and "estimate-memo.md" not in paths
    est = next(o for o in res["outputs"] if o["path"] == "estimate.json")
    assert est["sha256"] and est["bytes"] > 100 and json.loads(est["content_text"])
    assert res["usage"] is None and res["cost"]["usd"] is None
    assert "model-json.stderr.txt" in res["logs"] or "model-json" in res["logs"]
    assert res["model"] is None
    assert not (rt.WORK_ROOT / "t-repo-1").exists(), "per-run folder is removed"


def test_missing_required_input_is_needs_input_not_failure(rt):
    res = rt.execute({"run_id": "t-needs", "skill": {"kind": "repo", "repo_skill": "presales/effort-estimator"},
                      "inputs": {"client": {"kind": "value", "value": "Acme"}}, "provider": "none"})
    assert res["status"] == "needs_input" and res["exit_code"] == 2
    assert [m["name"] for m in res["needs_input"]["missing"]] == ["wbs"]
    assert "wbs" in res["error"]


def test_fixture_inputs_and_eval_case_checks(rt):
    res = rt.execute({
        "run_id": "t-fixture", "skill": {"kind": "repo", "repo_skill": "presales/effort-estimator"},
        "inputs": {"wbs": {"kind": "fixture", "path": "evals/fixtures/wbs.csv"}, "rates": {"kind": "fixture", "path": "evals/fixtures/rates.csv"},
                   "client": {"kind": "value", "value": "Acme"}},
        "provider": "none",
        "checks": ["exit:1", "exists:estimate.json", {"file": "estimate.md", "check": "contains:\"Cost and price (from supplied rate card)\""},
                   "exists:estimate-memo.md"],
    })
    cc = res["case_checks"]
    assert [c["pass"] for c in cc] == [True, True, True, False], cc
    assert "estimate-memo.md" in cc[3]["evidence"] or "missing" in cc[3]["evidence"].lower()


def test_fixture_traversal_rejected(rt):
    res = rt.execute({"run_id": "t-trav", "skill": {"kind": "repo", "repo_skill": "presales/effort-estimator"},
                      "inputs": {"wbs": {"kind": "fixture", "path": "evals/fixtures/../../SKILL.md"}}, "provider": "none"})
    assert res["status"] == "failed" and "bad fixture path" in res["error"]
    res = rt.execute({"run_id": "t-unknown", "skill": {"kind": "repo", "repo_skill": "nope/nope"}, "inputs": {}, "provider": "none"})
    assert res["status"] == "failed" and "unknown repo skill" in res["error"]


AUTHORED = {
    "purpose": "Count the rows of a CSV and write a JSON summary",
    "inputs": [{"name": "data", "type": "csv", "required": True, "from": "any CSV with a header"},
               {"name": "label", "type": "string", "required": False, "default": "rows"}],
    "run": [{"step": "count", "kind": "script", "cmd": "python3 scripts/count.py {data} --label {label}", "stdout": "{out}/summary.json"}],
    "outputs": [{"path": "{out}/summary.json", "checks": ["exists", "json", "contains:\"rows\""]}],
    "instructions_md": "# CSV counter\n\nCounts rows. Deterministic; no model needed.\n",
}
COUNT_PY = """import csv, json, sys, argparse
ap = argparse.ArgumentParser(); ap.add_argument("path"); ap.add_argument("--label", default="rows")
a = ap.parse_args()
with open(a.path, newline="", encoding="utf-8") as f:
    n = sum(1 for _ in csv.DictReader(f))
print(json.dumps({a.label: n, "status": "ok"}))
"""


def test_authored_skill_renders_skill_md_and_runs(rt):
    res = rt.execute({"run_id": "t-auth", "skill": {"kind": "authored", "slug": "csv-counter", "manifest": AUTHORED,
                                                     "files": [{"path": "scripts/count.py", "content": COUNT_PY}]},
                      "inputs": {"data": {"kind": "text", "content": "a,b\n1,2\n3,4\n", "ext": "csv"}}, "provider": "none"})
    assert res["status"] == "succeeded", (res["error"], res["logs"])
    out = next(o for o in res["outputs"] if o["path"] == "summary.json")
    assert json.loads(out["content_text"]) == {"rows": 2, "status": "ok"}
    assert all(c["pass"] for c in res["run_json"]["checks"])
    assert res["run_json"]["skill"] == "authored/csv-counter"


def test_render_skill_md_round_trips_through_skillmeta(rt, tmp_path):
    md = rt.render_skill_md("csv-counter", {**AUTHORED, "outputs": [{"path": "{out}/x.md", "checks": ["sections:[\"Bottom line\",\"Risks\"]", "exists"]}]})
    sys.path.insert(0, str(STUDIO.parent / "scripts"))
    try:
        import skillmeta  # repo parser
    finally:
        sys.path.pop(0)
    p = tmp_path / "SKILL.md"
    p.write_text(md, encoding="utf-8")
    agent = skillmeta.agent_block(skillmeta.load_skill(p))
    assert [i["name"] for i in agent["inputs"]] == ["data", "label"]
    assert agent["inputs"][0]["required"] is True and agent["inputs"][1]["default"] == "rows"
    assert agent["run"][0]["cmd"] == AUTHORED["run"][0]["cmd"]
    assert agent["outputs"][0]["checks"] == ['sections:["Bottom line","Risks"]', "exists"]


def test_authored_bad_file_path_rejected(rt):
    res = rt.execute({"run_id": "t-badfile", "skill": {"kind": "authored", "slug": "x", "manifest": AUTHORED,
                                                        "files": [{"path": "../scripts/evil.py", "content": ""}]}, "inputs": {}, "provider": "none"})
    assert res["status"] == "failed" and "bad file path" in res["error"]


def test_deadline_is_enforced(rt):
    slow = {**AUTHORED, "run": [{"step": "sleep", "kind": "script", "cmd": "python3 scripts/slow.py", "stdout": "{out}/summary.json"},
                                {"step": "after", "kind": "script", "cmd": "python3 scripts/count.py {data}", "stdout": "{out}/after.json"}]}
    t0 = time.time()
    res = rt.execute({"run_id": "t-timeout", "skill": {"kind": "authored", "slug": "slow", "manifest": slow,
                                                        "files": [{"path": "scripts/slow.py", "content": "import time\ntime.sleep(20)\nprint('{}')\n"},
                                                                  {"path": "scripts/count.py", "content": COUNT_PY}]},
                      "inputs": {"data": {"kind": "text", "content": "a,b\n1,2\n", "ext": "csv"}}, "provider": "none", "timeout_s": 1})
    assert time.time() - t0 < 10
    assert res["status"] == "timeout" and "deadline of 1s" in res["error"]
    assert not any(o["path"] == "after.json" for o in res["outputs"]), "no step runs after the deadline"


def test_environment_is_scrubbed_during_the_run(rt, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "should-not-leak")
    leak = {**AUTHORED, "run": [{"step": "env", "kind": "script", "cmd": "python3 scripts/env.py", "stdout": "{out}/summary.json"}]}
    res = rt.execute({"run_id": "t-env", "skill": {"kind": "authored", "slug": "env", "manifest": leak,
                                                    "files": [{"path": "scripts/env.py", "content": "import os, json\nprint(json.dumps({'rows': 0, 'env': sorted(os.environ)}))\n"}]},
                      "inputs": {"data": {"kind": "text", "content": "a,b\n", "ext": "csv"}}, "provider": "none"})
    env = json.loads(next(o for o in res["outputs"] if o["path"] == "summary.json")["content_text"])["env"]
    assert "ANTHROPIC_API_KEY" not in env and "SUPABASE_SERVICE_ROLE_KEY" not in env
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-secret", "restored afterwards"


def test_anthropic_callback_records_provider_usage_and_estimates_cost(rt, monkeypatch):
    """The HTTP call is replaced; everything after the provider reply (usage, model, cost estimate) is real."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        assert req.get_header("X-api-key") == "sk-ant-test"
        body = json.loads(req.data)
        return FakeResp(json.dumps({"model": body["model"] + "-20250929", "usage": {"input_tokens": 1200, "output_tokens": 300},
                                    "content": [{"type": "text", "text": "# Memo\n\n## Bottom line\n\nok\n"}]}).encode())
    monkeypatch.setattr(rt.urllib.request, "urlopen", fake_urlopen)
    m = {**AUTHORED, "run": [{"step": "memo", "kind": "llm", "template": "assets/t.md", "context": [], "out": "{out}/summary.json"}],
         "outputs": [{"path": "{out}/summary.json", "checks": ["exists"]}]}
    res = rt.execute({"run_id": "t-llm", "skill": {"kind": "authored", "slug": "llm", "manifest": m,
                                                    "files": [{"path": "assets/t.md", "content": "# Memo\n\n## Bottom line\n"}]},
                      "inputs": {"data": {"kind": "text", "content": "a,b\n", "ext": "csv"}}, "provider": "anthropic", "model": "claude-haiku-4-5"})
    assert res["status"] == "succeeded", (res["error"], res["logs"])
    assert res["provider"]["used"] == "anthropic" and res["model"] == "claude-haiku-4-5-20250929"
    assert res["usage"] == {"input_tokens": 1200, "output_tokens": 300, "calls": 1, "retries": 0, "source": "provider-reported"}
    assert res["cost"]["is_estimate"] is True and abs(res["cost"]["usd"] - (1200 * 1.0 + 300 * 5.0) / 1e6) < 1e-9
    assert "price table" in res["cost"]["basis"]


def test_anthropic_retry_is_bounded(rt, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    calls = {"n": 0}
    def flaky(req, timeout=0):  # noqa: ARG001
        calls["n"] += 1
        raise rt.urllib.error.HTTPError(rt.ANTHROPIC_URL, 529, "overloaded", {}, io.BytesIO(b'{"error":{"message":"Overloaded"}}'))
    monkeypatch.setattr(rt.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(rt.time, "sleep", lambda *_: None)
    m = {**AUTHORED, "run": [{"step": "memo", "kind": "llm", "template": "assets/t.md", "out": "{out}/summary.json"}]}
    res = rt.execute({"run_id": "t-retry", "skill": {"kind": "authored", "slug": "llm", "manifest": m, "files": [{"path": "assets/t.md", "content": "# T\n"}]},
                      "inputs": {"data": {"kind": "text", "content": "a,b\n", "ext": "csv"}}, "provider": "anthropic", "max_retries": 2})
    assert calls["n"] == 3 and res["status"] == "failed"
    assert "provider error: anthropic HTTP 529" in res["run_json"]["steps"][0]["error"]


def test_handler_requires_the_shared_secret(rt, monkeypatch):
    class H(rt.handler):
        def __init__(self, headers, body=b""):  # noqa: D107 — bypass socket setup
            self.headers = headers
            self.rfile = io.BytesIO(body)
            self.wfile = io.BytesIO()
            self.sent = []
        def send_response(self, code): self.sent.append(code)
        def send_header(self, *a): pass
        def end_headers(self): pass
    monkeypatch.delenv("SF_RUNTIME_SECRET", raising=False)
    h = H({}); h.do_GET()
    assert h.sent == [503] and b"SF_RUNTIME_SECRET" in h.wfile.getvalue()
    monkeypatch.setenv("SF_RUNTIME_SECRET", "s3cret")
    h = H({"x-sf-runtime-secret": "wrong"}); h.do_GET()
    assert h.sent == [401]
    h = H({"x-sf-runtime-secret": "s3cret"}); h.do_GET()
    assert h.sent == [200] and json.loads(h.wfile.getvalue())["bundle_files"] > 400
    body = json.dumps({"run_id": "t-http", "skill": {"kind": "repo", "repo_skill": "presales/effort-estimator"}, "inputs": {}, "provider": "none"}).encode()
    h = H({"x-sf-runtime-secret": "s3cret", "content-length": str(len(body))}, body); h.do_POST()
    assert h.sent == [200] and json.loads(h.wfile.getvalue())["status"] == "needs_input"


def test_openai_compat_callback_uses_base_url_and_records_usage(rt, monkeypatch):
    """provider openai_compat (e.g. Groq free tier): Bearer key, /chat/completions on SF_LLM_BASE_URL, usage from prompt/completion tokens."""
    monkeypatch.setenv("SF_LLM_API_KEY", "gsk-test")
    monkeypatch.setenv("SF_LLM_BASE_URL", "https://example.test/openai/v1/")
    seen = {}
    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        seen["url"], seen["auth"] = req.full_url, req.get_header("Authorization")
        body = json.loads(req.data)
        assert body["messages"][0]["role"] == "system" and body["messages"][1]["role"] == "user"
        return FakeResp(json.dumps({"model": body["model"], "usage": {"prompt_tokens": 900, "completion_tokens": 200},
                                    "choices": [{"message": {"role": "assistant", "content": "# Memo\n\n## Bottom line\n\nok\n"}}]}).encode())
    monkeypatch.setattr(rt.urllib.request, "urlopen", fake_urlopen)
    m = {**AUTHORED, "run": [{"step": "memo", "kind": "llm", "template": "assets/t.md", "context": [], "out": "{out}/summary.json"}],
         "outputs": [{"path": "{out}/summary.json", "checks": ["exists"]}]}
    res = rt.execute({"run_id": "t-compat", "skill": {"kind": "authored", "slug": "llm", "manifest": m,
                                                       "files": [{"path": "assets/t.md", "content": "# Memo\n\n## Bottom line\n"}]},
                      "inputs": {"data": {"kind": "text", "content": "a,b\n", "ext": "csv"}}, "provider": "openai_compat", "model": "llama-3.3-70b-versatile"})
    assert res["status"] == "succeeded", (res["error"], res["logs"])
    assert seen == {"url": "https://example.test/openai/v1/chat/completions", "auth": "Bearer gsk-test"}
    assert res["provider"]["used"] == "openai_compat"
    assert res["usage"]["input_tokens"] == 900 and res["usage"]["output_tokens"] == 200 and res["usage"]["calls"] == 1
    assert res["cost"]["usd"] is None  # no price-table entry: free tier is not assumed to be free forever


def test_openai_compat_without_key_skips_llm_honestly(rt, monkeypatch):
    monkeypatch.delenv("SF_LLM_API_KEY", raising=False)
    m = {**AUTHORED, "run": [{"step": "memo", "kind": "llm", "template": "assets/t.md", "context": [], "out": "{out}/summary.json"}],
         "outputs": [{"path": "{out}/summary.json", "checks": ["exists"]}]}
    res = rt.execute({"run_id": "t-compat-nokey", "skill": {"kind": "authored", "slug": "llm", "manifest": m,
                                                             "files": [{"path": "assets/t.md", "content": "# Memo\n"}]},
                      "inputs": {"data": {"kind": "text", "content": "a,b\n", "ext": "csv"}}, "provider": "openai_compat", "model": "llama-3.3-70b-versatile"})
    assert res["status"] == "failed" and res["provider"]["used"] == "none" and "SF_LLM_API_KEY" in res["provider"]["note"]


def test_openai_compat_drops_rejected_params_and_prices_from_env(rt, monkeypatch):
    """OpenAI reasoning models reject a custom temperature: the call is retried once without it. Price comes from env."""
    monkeypatch.setenv("SF_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("SF_LLM_BASE_URL", "https://api.openai.example/v1")
    monkeypatch.setenv("SF_LLM_PRICE_IN", "0.10")
    monkeypatch.setenv("SF_LLM_PRICE_OUT", "0.50")
    bodies = []
    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        body = json.loads(req.data); bodies.append(body)
        if "temperature" in body:
            raise rt.urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b'{"error":{"message":"Unsupported value: \'temperature\' does not support 0.2"}}'))
        return FakeResp(json.dumps({"model": body["model"], "usage": {"prompt_tokens": 1000, "completion_tokens": 400},
                                    "choices": [{"message": {"content": "# Memo\\n"}}]}).encode())
    monkeypatch.setattr(rt.urllib.request, "urlopen", fake_urlopen)
    m = {**AUTHORED, "run": [{"step": "memo", "kind": "llm", "template": "assets/t.md", "context": [], "out": "{out}/summary.json"}],
         "outputs": [{"path": "{out}/summary.json", "checks": ["exists"]}]}
    res = rt.execute({"run_id": "t-oai", "skill": {"kind": "authored", "slug": "llm", "manifest": m, "files": [{"path": "assets/t.md", "content": "# Memo\n"}]},
                      "inputs": {"data": {"kind": "text", "content": "a,b\n", "ext": "csv"}}, "provider": "openai_compat", "model": "cheap-model"})
    assert res["status"] == "succeeded", (res["error"], res["logs"])
    assert len(bodies) == 2 and "temperature" not in bodies[1] and bodies[1]["max_completion_tokens"] > 0
    assert res["usage"]["retries"] == 0
    assert abs(res["cost"]["usd"] - (1000 * 0.10 + 400 * 0.50) / 1e6) < 1e-12 and "SF_LLM_PRICE" in res["cost"]["basis"]
