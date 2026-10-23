"""scripts/llm_builder.py — the openai-compat builder: the file-block protocol, the endpoint guard, and a loopback
stub of an OpenAI-compatible server (StubLLM, also used by test_deliver.py) that answers each role packet with canned
FILE blocks taken from the delivery fixtures. No real model, no network beyond 127.0.0.1."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from conftest import REPO_ROOT, run_script

SCRIPT = REPO_ROOT / "scripts" / "llm_builder.py"
FIX = REPO_ROOT / "tests" / "fixtures"
REPO = FIX / "delivery-repo"
BUILD = FIX / "delivery-build"
_REAL_SOCKET = socket.socket   # captured at import, before conftest's no_network fixture replaces it


def load_module():
    spec = importlib.util.spec_from_file_location("llm_builder_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def file_block(path: str, content: str) -> str:
    return f"=== FILE: {path} ===\n{content.rstrip(chr(10))}\n=== END FILE ===\n"


def patched_files(patch: Path = BUILD / "diff.patch") -> dict[str, str]:
    """The full content of every file the fixture diff touches, after the diff: what a model that writes whole files
    would answer for the code step (the delivery-repo copy is throwaway)."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / "repo"
        shutil.copytree(REPO, work)
        body = "\n".join(ln for ln in patch.read_text().splitlines() if not ln.startswith("# ")) + "\n"
        (Path(td) / "p.patch").write_text(body)
        subprocess.run(["git", "apply", str(Path(td) / "p.patch")], cwd=work, check=True, capture_output=True,
                       env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        paths = sorted({ln[6:].strip() for ln in body.splitlines() if ln.startswith("+++ b/")})
        return {p: (work / p).read_text() for p in paths}


def canned_code_reply(files: dict[str, str] | None = None) -> str:
    return "".join(file_block(p, c) for p, c in (files or patched_files()).items())


CANNED = {
    "prd-refine": file_block("prd-final.md", (BUILD / "prd-final.md").read_text()),
    "plan-refine": file_block("plan.md", (BUILD / "plan" / "plan.md").read_text()) + file_block("tasks.csv", (BUILD / "plan" / "tasks.csv").read_text()),
    "files": file_block("files.txt", (BUILD / "files.txt").read_text()),
}


class StubLLM:
    """A loopback /v1/chat/completions server. The role is read from the packet's title line
    (`# Role: <role> — step <id> …`); `replies[step]` is one canned reply or a list consumed per call (the repair
    round gets the second). Every request body is kept in `calls`."""

    def __init__(self, replies: dict | None = None, status: int = 200):
        self.replies = {k: (list(v) if isinstance(v, list) else [v]) for k, v in {**CANNED, **(replies or {})}.items()}
        self.calls: list[dict] = []
        self.status = status
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                stub.calls.append({"path": self.path, "auth": self.headers.get("Authorization", ""), "body": body})
                if stub.status != 200:
                    data = json.dumps({"error": {"message": "stub failure"}}).encode()
                    self.send_response(stub.status); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
                    return
                packet = next((m["content"] for m in body.get("messages", []) if m.get("role") == "user"), "")
                title = packet.splitlines()[0] if packet else ""
                step = next((s for s in stub.replies if f"step {s} " in title or title.endswith(f"step {s}")), None)
                queue = stub.replies.get(step) or ["(no canned reply for this packet)"]
                text = queue.pop(0) if len(queue) > 1 else queue[0]
                data = json.dumps({"id": "stub", "object": "chat.completion", "model": body.get("model"),
                                   "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

        socket.socket = _REAL_SOCKET   # loopback only; conftest's monkeypatch restores the block at teardown
        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown(); self.server.server_close()


def llm_env(monkeypatch, stub: StubLLM | None = None):
    """A clean endpoint environment: no proxy can swallow the loopback call, no inherited OPENAI_* leaks in."""
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    if stub:
        monkeypatch.setenv("OPENAI_BASE_URL", stub.base_url)


@pytest.fixture
def stub():
    s = StubLLM()
    yield s
    s.close()


# ---------------------------------------------------------------- parse_file_blocks

def test_parse_file_blocks_reads_every_block_whole_and_keeps_order():
    m = load_module()
    text = ("Here you go:\n" + file_block("lib/orders.js", "export const a = 1;\n\nexport const b = 2;")
            + "\n" + file_block("app/api/orders/export/route.js", "export async function GET() {}") + "=== DELETE: lib/old.js ===\n")
    blocks = m.parse_file_blocks(text)
    assert [p for p, _ in blocks] == ["lib/orders.js", "app/api/orders/export/route.js", "lib/old.js"]
    assert blocks[0][1] == "export const a = 1;\n\nexport const b = 2;\n"       # blank lines inside the body kept, one trailing newline
    assert blocks[1][1] == "export async function GET() {}\n" and blocks[2][1] is None


def test_parse_file_blocks_strips_reasoning_and_tolerates_backticked_paths():
    m = load_module()
    reply = "<think>let me plan</think>\n" + file_block("`./lib/orders.js`", "x")
    assert m.parse_file_blocks(m.strip_reasoning(reply)) == [("lib/orders.js", "x\n")]
    assert m.strip_reasoning("<think>never closed") == ""


@pytest.mark.parametrize("bad", ["../etc/passwd", "/etc/passwd", "lib/../../x.js", "C:\\x.js", "lib\\orders.js", "~/x"])
def test_parse_file_blocks_refuses_traversal_and_absolute_paths(bad):
    m = load_module()
    with pytest.raises(m.LLMBuildError, match="refused path"):
        m.parse_file_blocks(file_block(bad, "x"))
    with pytest.raises(m.LLMBuildError, match="refused path"):
        m.parse_file_blocks(f"=== DELETE: {bad} ===\n")


def test_parse_file_blocks_enforces_the_allowlist_plus_test_paths():
    m = load_module()
    allowed = ["lib/orders.js"]
    ok = file_block("lib/orders.js", "a") + file_block("tests/unit/orders.test.js", "t") + file_block("__tests__/x.test.js", "t")
    assert [p for p, _ in m.parse_file_blocks(ok, allowed)] == ["lib/orders.js", "tests/unit/orders.test.js", "__tests__/x.test.js"]
    with pytest.raises(m.LLMBuildError, match="not in the allowed files"):
        m.parse_file_blocks(file_block("lib/other.js", "a"), allowed)
    with pytest.raises(m.LLMBuildError, match="no `=== FILE"):
        m.parse_file_blocks("I would write lib/orders.js like this: ```js\n```")


def test_a_delete_line_inside_a_file_body_is_content_not_a_directive():
    m = load_module()
    body = "notes:\n=== DELETE: lib/x.js ===\nend"
    assert m.parse_file_blocks(file_block("README.md", body)) == [("README.md", body + "\n")]


# ---------------------------------------------------------------- the client and its guard

def test_guard_refuses_a_non_openai_model_without_a_base_url_before_any_call(monkeypatch):
    m = load_module()
    with pytest.raises(m.OpenAICompatError, match="not an OpenAI model and no base URL"):
        m.OpenAICompat("qwen2.5-coder:14b", None, env={"OPENAI_API_KEY": "x"})      # socket is blocked: no call was attempted
    with pytest.raises(m.OpenAICompatError, match="no model"):
        m.OpenAICompat(None, None, env={"OPENAI_API_KEY": "x"})
    with pytest.raises(m.OpenAICompatError, match="OPENAI_API_KEY is not set"):
        m.OpenAICompat("gpt-4o-mini", None, env={})
    c = m.OpenAICompat("qwen2.5-coder:14b", "http://localhost:11434/v1/", env={"OPENAI_API_KEY": "ollama"})
    assert c.base_url == "http://localhost:11434/v1" and c.host == "localhost" and c.model == "qwen2.5-coder:14b"
    c = m.OpenAICompat(None, None, env={"OPENAI_API_KEY": "ollama", "OPENAI_BASE_URL": "http://127.0.0.1:11434/v1", "OPENAI_MODEL": "llama3"})
    assert c.model == "llama3"


def test_deliver_guard_exits_2_before_creating_the_run_directory(tmp_path, monkeypatch):
    llm_env(monkeypatch)
    out = tmp_path / "guard"
    r = run_script("scripts/deliver.py", "feature-delivery", "--repo", str(REPO), "--request", "x", "--out", str(out),
                   "--provider", "dry", "--dry", "--builder", "openai-compat", "--model", "qwen2.5-coder:14b")
    assert r.returncode == 2 and "not an OpenAI model and no base URL" in r.stderr, r.stdout + r.stderr
    assert not out.exists()


def test_chat_posts_the_model_the_key_and_the_messages(monkeypatch, stub):
    llm_env(monkeypatch, stub)
    m = load_module()
    c = m.OpenAICompat("stub", stub.base_url)
    reply = c.chat("be brief", "# Role: builder — step files (run r, pipeline p)", max_tokens=50)
    assert reply.startswith("=== FILE: files.txt ===")
    call = stub.calls[-1]
    assert call["path"] == "/v1/chat/completions" and call["auth"] == "Bearer stub-key"
    assert call["body"]["model"] == "stub" and call["body"]["max_tokens"] == 50 and call["body"]["temperature"] == 0
    assert [x["role"] for x in call["body"]["messages"]] == ["system", "user"]


def test_chat_retries_a_5xx_twice_then_raises(monkeypatch):
    llm_env(monkeypatch)
    s = StubLLM(status=503)
    try:
        m = load_module()
        c = m.OpenAICompat("stub", s.base_url)
        c.backoff_s = 0
        with pytest.raises(m.OpenAICompatError, match="HTTP 503"):
            c.chat("s", "u")
        assert len(s.calls) == 3
    finally:
        s.close()


def test_chat_does_not_retry_a_4xx(monkeypatch):
    llm_env(monkeypatch)
    s = StubLLM(status=401)
    try:
        m = load_module()
        c = m.OpenAICompat("stub", s.base_url)
        with pytest.raises(m.OpenAICompatError, match="HTTP 401"):
            c.chat("s", "u")
        assert len(s.calls) == 1
    finally:
        s.close()


# ---------------------------------------------------------------- run_role

def test_run_role_writes_the_produced_files_to_the_step_dir_and_records_the_round(tmp_path, monkeypatch, stub):
    llm_env(monkeypatch, stub)
    m = load_module()
    c = m.OpenAICompat("stub", stub.base_url)
    out = tmp_path / "plan-refine"
    res = m.run_role("# Role: architect — step plan-refine (run r, pipeline p)\n\nfill the plan", produce=["plan.md", "tasks.csv"],
                     allowed=None, out_dir=out, target=None, client=c)
    assert res["ok"] and res["rounds"] == 1 and res["files"] == ["plan.md", "tasks.csv"]
    assert (out / "tasks.csv").read_text() == (BUILD / "plan" / "tasks.csv").read_text()
    rounds = json.loads((out / "llm-rounds.json").read_text())
    assert rounds["provider"] == "openai-compat" and rounds["model"] == "stub" and rounds["base_url_host"] == "127.0.0.1"
    assert rounds["ok"] is True and [r["files"] for r in rounds["rounds"]] == [["plan.md", "tasks.csv"]]
    assert rounds["rounds"][0]["prompt_chars"] > 0 and rounds["rounds"][0]["reply_chars"] > 0
    assert (out / "llm-reply-1.txt").read_text() == CANNED["plan-refine"].strip()
    system = stub.calls[-1]["body"]["messages"][0]["content"]
    assert "=== FILE: <path> ===" in system and "`plan.md`, `tasks.csv`" in system


def test_run_role_asks_again_when_a_produced_file_is_missing_then_fails_naming_the_reply(tmp_path, monkeypatch):
    llm_env(monkeypatch)
    s = StubLLM({"plan-refine": ["Sure! Here is the plan in prose.", file_block("plan.md", "# plan")]})
    try:
        m = load_module()
        c = m.OpenAICompat("stub", s.base_url)
        out = tmp_path / "pr"
        with pytest.raises(m.LLMBuildError, match=r"did not produce tasks.csv. Reply head: '=== FILE: plan.md"):
            m.run_role("# Role: architect — step plan-refine (run r, pipeline p)", produce=["plan.md", "tasks.csv"], allowed=None,
                       out_dir=out, target=None, client=c, max_rounds=2)
        assert len(s.calls) == 2
        turns = s.calls[1]["body"]["messages"]
        assert [t["role"] for t in turns] == ["system", "user", "assistant", "user"] and "could not be used" in turns[-1]["content"]
        rounds = json.loads((out / "llm-rounds.json").read_text())
        assert rounds["ok"] is False and "no `=== FILE" in rounds["rounds"][0]["error"] and rounds["rounds"][1]["files"] == ["plan.md"]
        assert "did not produce tasks.csv" in rounds["error"]
    finally:
        s.close()


def test_run_role_code_step_lands_files_in_the_checkout_and_repairs_on_a_failing_command(tmp_path, monkeypatch):
    llm_env(monkeypatch)
    full = patched_files()
    first = canned_code_reply({"app/api/orders/export/route.js": full["app/api/orders/export/route.js"]})   # forgot lib/orders.js
    second = canned_code_reply({"lib/orders.js": full["lib/orders.js"]})
    s = StubLLM({"code": [first, second]})
    try:
        m = load_module()
        c = m.OpenAICompat("stub", s.base_url)
        work = tmp_path / "repo"
        shutil.copytree(REPO, work)
        out = tmp_path / "code"
        res = m.run_role("# Role: builder — step code (run r, pipeline p)", produce=[], allowed=["lib/orders.js", "app/api/orders/export/route.js"],
                         out_dir=out, target=work, client=c, max_rounds=2, repair_cmd="grep -q ordersToCsv lib/orders.js")
        assert res["ok"] and res["rounds"] == 2 and res["cmd_exit"] == 0
        assert res["files"] == ["app/api/orders/export/route.js", "lib/orders.js"]
        assert "ordersToCsv" in (work / "lib" / "orders.js").read_text()
        rounds = json.loads((out / "llm-rounds.json").read_text())
        assert [(r["round"], r["cmd_exit"], r["files"]) for r in rounds["rounds"]] == [
            (1, 1, ["app/api/orders/export/route.js"]), (2, 0, ["lib/orders.js"])]
        assert rounds["repair_cmd"] == "grep -q ordersToCsv lib/orders.js"
        repair = s.calls[1]["body"]["messages"][-1]["content"]
        assert repair.startswith("`grep -q ordersToCsv lib/orders.js` exited 1") and "complete FILE blocks" in repair
        assert (out / "llm-reply-2.txt").read_text() == second.strip() and (out / "llm-cmd-1.txt").is_file()
        system = s.calls[0]["body"]["messages"][0]["content"]
        assert "- lib/orders.js\n- app/api/orders/export/route.js" in system and "tests/, __tests__/ or e2e/" in system
    finally:
        s.close()


def test_run_role_code_step_refuses_a_block_outside_the_allowed_files_and_writes_nothing(tmp_path, monkeypatch):
    llm_env(monkeypatch)
    s = StubLLM({"code": file_block("next.config.js", "module.exports = {}")})
    try:
        m = load_module()
        c = m.OpenAICompat("stub", s.base_url)
        work = tmp_path / "repo"
        shutil.copytree(REPO, work)
        before = (work / "next.config.js").read_text()
        with pytest.raises(m.LLMBuildError, match="refused path 'next.config.js': not in the allowed files"):
            m.run_role("# Role: builder — step code (run r, pipeline p)", produce=[], allowed=["lib/orders.js"], out_dir=tmp_path / "o",
                       target=work, client=c, max_rounds=1)
        assert (work / "next.config.js").read_text() == before
    finally:
        s.close()


def test_run_role_exhausted_repair_rounds_fail_with_the_command_tail(tmp_path, monkeypatch):
    llm_env(monkeypatch)
    s = StubLLM({"code": file_block("lib/orders.js", "export const nothing = 1;")})
    try:
        m = load_module()
        c = m.OpenAICompat("stub", s.base_url)
        work = tmp_path / "repo"
        shutil.copytree(REPO, work)
        with pytest.raises(m.LLMBuildError, match=r"`sh -c 'echo boom >&2; exit 3'` still exits 3 after 2 round\(s\); output tail: 'boom"):
            m.run_role("# Role: builder — step code (run r, pipeline p)", produce=[], allowed=["lib/orders.js"], out_dir=tmp_path / "o",
                       target=work, client=c, max_rounds=2, repair_cmd="sh -c 'echo boom >&2; exit 3'")
        assert len(s.calls) == 2
    finally:
        s.close()
