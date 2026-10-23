#!/usr/bin/env python3
"""The `openai-compat` builder for scripts/deliver.py — any OpenAI-compatible model plays the product-manager,
architect and builder roles (docs/DELIVERY-PIPELINES.md → "Any LLM").

The customer's own model answers the role packet (PROMPT.md, the same text every builder gets): Ollama, vLLM,
LM Studio, Azure OpenAI, Bedrock or LiteLLM proxies — anything that serves POST <base>/chat/completions. Stdlib only
(urllib), no SDK, no new dependency.

    OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama \\
    python3 scripts/deliver.py feature-delivery … --builder openai-compat --model qwen2.5-coder:14b

Output protocol (stated in the system prompt, parsed by parse_file_blocks): the model answers ONLY with file blocks

    === FILE: <repo-relative path> ===
    <full file content>
    === END FILE ===

and optionally `=== DELETE: <path> ===`. A path with `..`, an absolute path, a backslash path or a path outside the
caller's allowlist is refused before anything is written. A reasoning model's <think>…</think> block is stripped.

run_role() sends the packet as the user message with a role-specific system prompt, writes the blocks — to the step
folder for prd-refine / plan-refine / files (the expected file names), into the checkout for the code step
(restricted to the allowed files plus test paths) — runs the repair command when one is given, and on a failing
command or an unparseable reply sends the output tail back as a repair turn, up to `max_rounds`. Every round is
recorded in <step dir>/llm-rounds.json and every raw reply in <step dir>/llm-reply-<n>.txt. Nothing from the
environment reaches a prompt: the packet is already clean and the system prompt is static text plus the file lists.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODEL_RE = re.compile(r"^(gpt-|o\d|chatgpt-|text-)")          # the names api.openai.com serves
TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|e2e)/")           # test files the code step may add beside files.txt
THINK_BLOCK = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S | re.I)
THINK_OPEN = re.compile(r"<think(?:ing)?>", re.I)
FILE_BLOCK_RE = re.compile(r"^[ \t]*=== FILE: (?P<path>[^\n]+?) ===[ \t]*\r?\n(?P<body>.*?)(?:\r?\n)?^[ \t]*=== END FILE ===[ \t]*$", re.M | re.S)
DELETE_RE = re.compile(r"^[ \t]*=== DELETE: (?P<path>[^\n]+?) ===[ \t]*$", re.M)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}
RETRIES = 2                                                           # on 5xx / timeout: 3 attempts in all
OUTPUT_TAIL = 4000                                                    # chars of a failing repair command fed back
REPLY_HEAD = 400                                                      # chars of a bad reply named in the error

PROTOCOL = """You are one role in a software delivery pipeline. The user message is a self-contained role packet: what to
produce, the gate it must pass, every input, the rules. Read it in full and do the work it asks.

ANSWER FORMAT — mandatory. Reply ONLY with one or more file blocks, nothing before, between or after them
(no commentary, no Markdown fences around the blocks, no partial files):

=== FILE: <path> ===
<the complete content of that file>
=== END FILE ===

To delete a file reply with a line `=== DELETE: <path> ===`. Paths are relative, forward-slash, never absolute,
never with `..`. Every FILE block holds the whole file, exactly as it should exist on disk. Where the packet says
something cannot be known, write what it says to write — never invent facts, paths or requirements."""


class OpenAICompatError(Exception):
    """The endpoint cannot be used as configured, or the call failed after its retries."""


class LLMBuildError(Exception):
    """The model's output did not produce what the step needs (parse failure, nothing written, repair exhausted)."""


def strip_reasoning(text: str | None) -> str:
    """The answer part of a reply: a local reasoning model may think in <think>…</think> first; an unclosed block has
    no answer at all."""
    text = THINK_BLOCK.sub("", text or "")
    m = THINK_OPEN.search(text)
    if m:
        text = text[:m.start()]
    return text.strip()


def is_local_endpoint(base_url: str) -> bool:
    """True when the base URL points anywhere but api.openai.com (Ollama, vLLM, a proxy, Azure…)."""
    return bool(base_url.strip()) and "api.openai.com" not in base_url


class OpenAICompat:
    """A chat-completions client over urllib. Model from `model` / OPENAI_MODEL, base URL from `base_url` /
    OPENAI_BASE_URL (default api.openai.com), key from OPENAI_API_KEY (any non-empty string for a local server).
    Guard: a model name api.openai.com does not serve, with no base URL set, is refused before any call is made —
    the request would otherwise go to OpenAI with the wrong model and the wrong key."""

    backoff_s = 1.0   # doubles per retry; tests set 0

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None, env=None):
        env = os.environ if env is None else env
        base = (base_url or env.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
        name = (model or env.get("OPENAI_MODEL") or "").strip()
        if not name:
            raise OpenAICompatError("no model: pass --model <name> or set OPENAI_MODEL")
        if not is_local_endpoint(base) and not OPENAI_MODEL_RE.match(name):
            raise OpenAICompatError(f"model '{name}' is not an OpenAI model and no base URL is set — this call would go to "
                                    "api.openai.com. For a local server: --base-url http://<host>:11434/v1 (or export "
                                    "OPENAI_BASE_URL) and OPENAI_API_KEY=ollama")
        key = (api_key if api_key is not None else env.get("OPENAI_API_KEY") or "").strip()
        if not key:
            raise OpenAICompatError("OPENAI_API_KEY is not set (any non-empty string for a local server, e.g. ollama)")
        self.base_url, self.model, self._key = base, name, key
        parts = urllib.parse.urlsplit(base)
        self.host = parts.hostname or base
        # a loopback / LAN model server is reached directly: an HTTP(S)_PROXY in the environment must not swallow it
        handlers = [urllib.request.ProxyHandler({})] if self.host in LOCAL_HOSTS else []
        self._opener = urllib.request.build_opener(*handlers)

    # -- calls
    def chat(self, system: str, user: str, *, max_tokens: int = 8192, temperature: float = 0, timeout_s: float = 600) -> str:
        return self.chat_messages([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                  max_tokens=max_tokens, temperature=temperature, timeout_s=timeout_s)

    def chat_messages(self, messages: list[dict], *, max_tokens: int = 8192, temperature: float = 0, timeout_s: float = 600) -> str:
        """POST /chat/completions with a full message list (the repair turns extend the conversation); the reply text
        with any reasoning block stripped. Retries RETRIES times on a 5xx or a timeout; a 4xx is final."""
        body = json.dumps({"model": self.model, "messages": messages, "temperature": temperature,
                           "max_tokens": max_tokens, "stream": False}).encode("utf-8")
        req = urllib.request.Request(self.base_url + "/chat/completions", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._key}",
                                              "Accept": "application/json"})
        last: Exception | None = None
        for attempt in range(RETRIES + 1):
            try:
                with self._opener.open(req, timeout=timeout_s) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:300] if e.fp else ""
                last = OpenAICompatError(f"{self.host} answered HTTP {e.code} on /chat/completions: {detail or e.reason}")
                if e.code < 500:
                    raise last from None
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
                reason = getattr(e, "reason", e)
                last = OpenAICompatError(f"{self.host} did not answer /chat/completions: {reason}")
            if attempt < RETRIES and self.backoff_s:
                time.sleep(self.backoff_s * (2 ** attempt))
        else:
            raise last or OpenAICompatError("no answer")
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"] if "message" in choice else choice.get("text", "")
        except (KeyError, IndexError, TypeError):
            raise OpenAICompatError(f"{self.host}: the reply is not a chat completion: {json.dumps(data)[:300]}") from None
        return strip_reasoning(content)


# -- the output protocol
def _clean_path(raw: str) -> str:
    p = raw.strip().strip("`'\"").strip()
    if p.startswith("./"):
        p = p[2:]
    return p


def _check_path(p: str, allowed: list[str] | None) -> None:
    if not p:
        raise LLMBuildError("a file block names an empty path")
    if "\\" in p or p.startswith("/") or re.match(r"^[A-Za-z]:", p) or p.startswith("~"):
        raise LLMBuildError(f"refused path {p!r}: paths must be relative with forward slashes")
    if any(seg == ".." for seg in p.split("/")) or any(seg == "" for seg in p.split("/")):
        raise LLMBuildError(f"refused path {p!r}: `..` and empty segments are not allowed")
    if allowed is not None and p not in allowed and not TEST_PATH_RE.search(p):
        raise LLMBuildError(f"refused path {p!r}: not in the allowed files ({', '.join(allowed) or 'none'}) nor a test path")


def parse_file_blocks(text: str, allowed: list[str] | None = None) -> list[tuple[str, str | None]]:
    """(path, content) per FILE block and (path, None) per DELETE line, in reply order, the last block of a path
    winning. Raises LLMBuildError on a refused path (traversal, absolute, outside `allowed` + test paths) and on a
    reply with no block at all."""
    found: dict[str, str | None] = {}
    for m in FILE_BLOCK_RE.finditer(text):
        p = _clean_path(m.group("path"))
        _check_path(p, allowed)
        body = m.group("body")
        found[p] = body if body.endswith("\n") or body == "" else body + "\n"
    # a DELETE line inside a FILE body is content, not a directive
    bodies = [m.span() for m in FILE_BLOCK_RE.finditer(text)]
    for m in DELETE_RE.finditer(text):
        if any(a <= m.start() < b for a, b in bodies):
            continue
        p = _clean_path(m.group("path"))
        _check_path(p, allowed)
        found[p] = None
    if not found:
        raise LLMBuildError("the reply holds no `=== FILE: … ===` block")
    return list(found.items())


def _tail(text: str, limit: int = OUTPUT_TAIL) -> str:
    text = text or ""
    return text if len(text) <= limit else "…" + text[-limit:]


def _system_prompt(produce: list[str], allowed: list[str] | None, target: Path | None) -> str:
    if target is None:
        names = ", ".join(f"`{n}`" for n in produce)
        return (PROTOCOL + f"\n\nTHIS STEP produces exactly these file(s): {names}. Use those names as the block paths, "
                "nothing else: one FILE block per file, every one of them, each with its complete content in the format the "
                "packet states. Do not write any other file.\n\nWhen the packet inlines a draft or scaffold of the file "
                "(under Inputs), START FROM THAT TEXT: keep every one of its headings and table columns exactly as written, "
                "fill the cells and sections, replace `[TO BE BASELINED …]` markers with what the request and inputs state, "
                "and return the whole file. Never invent a structure of your own — the gate checks the draft's headings.")
    allow = "\n".join(f"- {f}" for f in allowed) if allowed else "- (the packet's file list)"
    return (PROTOCOL + "\n\nTHIS STEP changes the repository checkout. Block paths are repo-relative. You may write ONLY "
            f"these files:\n{allow}\nplus test files under tests/, __tests__/ or e2e/. A FILE block for a file that exists "
            "replaces it whole: reproduce every line you keep. Make the red tests the packet names green; follow every "
            "constraint document in the packet; change nothing the packet does not ask for.")


def run_role(packet_text: str, *, produce: list[str], allowed: list[str] | None, out_dir: Path, target: Path | None,
             client: OpenAICompat, max_rounds: int = 2, repair_cmd: str | None = None, max_tokens: int = 16000,
             checks: list[tuple[str, str]] | None = None, check_fn=None,
             timeout_s: float = 900, cmd_timeout_s: float = 1800) -> dict:
    """One role, one packet, up to `max_rounds` model turns. target None → a document step: the blocks named in
    `produce` are written to out_dir. target set → the code step: blocks land in the checkout (allowed + test paths),
    then `repair_cmd` runs there; a failing command's output tail is the next user turn. Returns the record also
    written to out_dir/llm-rounds.json; raises LLMBuildError when the rounds are spent without a usable result."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rounds = max(1, int(max_rounds))
    system = _system_prompt(produce, allowed, target)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": packet_text}]
    record = {"provider": "openai-compat", "model": client.model, "base_url_host": client.host, "max_rounds": rounds,
              "repair_cmd": repair_cmd or None, "rounds": [], "ok": False}
    written_all: list[str] = []
    deleted_all: list[str] = []

    def save() -> None:
        (out_dir / "llm-rounds.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    def fail(msg: str) -> LLMBuildError:
        record["error"] = msg
        save()
        return LLMBuildError(msg)

    for n in range(1, rounds + 1):
        prompt_chars = sum(len(m["content"]) for m in messages)
        t0 = time.time()
        try:
            reply = client.chat_messages(messages, max_tokens=max_tokens, temperature=0, timeout_s=timeout_s)
        except OpenAICompatError as e:
            record["rounds"].append({"round": n, "prompt_chars": prompt_chars, "reply_chars": 0, "files": [], "error": str(e)})
            raise fail(f"round {n}: {e}") from None
        (out_dir / f"llm-reply-{n}.txt").write_text(reply, encoding="utf-8")
        rnd = {"round": n, "prompt_chars": prompt_chars, "reply_chars": len(reply), "files": [], "deleted": [],
               "duration_s": round(time.time() - t0, 3)}
        record["rounds"].append(rnd)
        messages.append({"role": "assistant", "content": reply})
        try:
            blocks = parse_file_blocks(reply, allowed if target is not None else None)
        except LLMBuildError as e:
            rnd["error"] = str(e)
            problem = f"{e}. Reply head: {reply[:REPLY_HEAD]!r}"
            if n == rounds:
                raise fail(f"round {n}: {problem}")
            messages.append({"role": "user", "content": f"Your reply could not be used: {e}. Answer again, ONLY with "
                                                        "`=== FILE: <path> ===` … `=== END FILE ===` blocks as instructed."})
            save()
            continue
        if target is None:
            wanted = {Path(p).name: p for p in produce}
            for p, content in blocks:
                name = wanted.get(Path(p).name)
                if name is None or content is None:
                    rnd.setdefault("ignored", []).append(p)
                    continue
                (out_dir / name).write_text(content, encoding="utf-8")
                rnd["files"].append(name)
                if name not in written_all:
                    written_all.append(name)
            missing = [p for p in produce if not (out_dir / p).is_file()]
            if not missing:
                # the gate's own checks on the documents, run here so a refusal is answered by the model, not the gate
                failed = []
                for fname, spec in (checks or []):
                    if check_fn is None or not (out_dir / fname).is_file():
                        continue
                    r = check_fn(out_dir / fname, spec)
                    if not r.get("pass"):
                        failed.append(f"{fname}: {spec} — {r.get('evidence')}")
                rnd["checks_failed"] = failed
                if not failed:
                    record.update(ok=True, files=written_all)
                    save()
                    return {"rounds": n, "files": written_all, "model": client.model, "base_url_host": client.host, "ok": True}
                problem = "the gate refuses the output: " + " | ".join(failed)
                if n == rounds:
                    raise fail(f"round {n}: {problem}")
                messages.append({"role": "user", "content": "The gate refused your file(s):\n- " + "\n- ".join(failed) +
                                 "\n\nFix exactly that and reply again with a complete FILE block for each file (keep the "
                                 "draft's headings verbatim; no prose outside the blocks)."})
                save()
                continue
            problem = f"the reply did not produce {', '.join(missing)}"
            if n == rounds:
                raise fail(f"round {n}: {problem}. Reply head: {reply[:REPLY_HEAD]!r}")
            messages.append({"role": "user", "content": f"Missing: {', '.join(missing)}. Reply with a complete FILE block for each "
                                                        "missing file (and nothing else)."})
            save()
            continue
        # the code step: land the blocks on the checkout
        for p, content in blocks:
            dest = target / p
            if content is None:
                if dest.is_file():
                    dest.unlink()
                rnd["deleted"].append(p)
                if p not in deleted_all:
                    deleted_all.append(p)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            rnd["files"].append(p)
            if p not in written_all:
                written_all.append(p)
        if not repair_cmd:
            record.update(ok=True, files=written_all, deleted=deleted_all)
            save()
            return {"rounds": n, "files": written_all, "deleted": deleted_all, "model": client.model, "base_url_host": client.host, "ok": True}
        rnd["cmd"] = repair_cmd
        try:
            r = subprocess.run(repair_cmd, shell=True, cwd=str(target), capture_output=True, text=True, timeout=cmd_timeout_s)
            exit_code, output = r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired as e:
            exit_code, output = 124, f"timed out after {cmd_timeout_s}s\n" + ((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        rnd["cmd_exit"] = exit_code
        (out_dir / f"llm-cmd-{n}.txt").write_text(output, encoding="utf-8")
        if exit_code == 0:
            record.update(ok=True, files=written_all, deleted=deleted_all, cmd_exit=0)
            save()
            return {"rounds": n, "files": written_all, "deleted": deleted_all, "model": client.model, "base_url_host": client.host,
                    "cmd_exit": 0, "ok": True}
        if n == rounds:
            record["cmd_exit"] = exit_code
            raise fail(f"`{repair_cmd}` still exits {exit_code} after {n} round(s); output tail: {_tail(output, 600)!r}")
        messages.append({"role": "user", "content": f"`{repair_cmd}` exited {exit_code} on the checkout after your change. "
                                                    f"Output tail:\n\n{_tail(output)}\n\nFix it: reply ONLY with complete FILE blocks "
                                                    "for every file that must change (and nothing else)."})
        save()
    raise fail("no rounds ran")   # unreachable: rounds >= 1
