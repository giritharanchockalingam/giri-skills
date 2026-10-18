"""Skills Factory runtime — Vercel Python Serverless Function (POST /api/py/run).

Executes one skill version with the repo's real runner (scripts/run_skill.py, in-process mode) inside the
function's /tmp, and returns run.json + outputs + logs + provider usage. Stdlib only.

Security model
  * Callers must present `x-sf-runtime-secret` equal to the SF_RUNTIME_SECRET environment variable; the Next.js
    server is the only intended caller (it has already authenticated the user / API key and validated inputs).
  * Skill files and their scripts are untrusted: they run inside a per-run folder under /tmp with the process
    environment scrubbed (only PATH/LANG/TMPDIR/HOME survive). The Anthropic key never enters the environment:
    it lives in a closure of the LLM callback and is passed only when the manifest's provider is "anthropic".
    Limitation (stated, not hidden): steps run in this interpreter (there is no subprocess on the runtime), so
    a malicious script shares the process; author/admin roles gate who can put scripts here.
  * Deadline: the manifest's limits.timeout_s (≤ 55 s) via SIGALRM on the main thread, or a worker thread join
    when the handler is not on the main thread. Retries: bounded by limits.max_retries, only on 429/5xx/network.

Request (JSON):
  {run_id, skill: {kind:"repo", repo_skill:"domain/name"} | {kind:"authored", slug, manifest, files:[{path,content}]},
   inputs: {name: {kind:"text",content,ext?} | {kind:"value",value} | {kind:"fixture",path}}, assumptions: {name: value},
   provider: "none"|"anthropic", model, temperature, max_tokens, timeout_s, max_retries, checks?: [eval-case checks]}
Response (JSON): see `execute()`; always HTTP 200 with a `status` field, or 4xx/5xx with {"error": ...}.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import importlib
import io
import json
import os
import re
import shutil
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE_CANDIDATES = [HERE / "bundle.json", HERE.parent.parent / "public" / "runtime" / "bundle.json"]
RUNTIME_VERSION = "vercel-python"
RUNNER_VERSION = "run_skill.py@inproc-1"
MAX_TIMEOUT_S = 55
MAX_CONTENT_TEXT = 200 * 1024
MAX_OUTPUT_FILES = 200
WORK_ROOT = Path(os.environ.get("SF_WORK_ROOT", "/tmp/sf"))
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_COMPAT_BASE_URL = "https://api.groq.com/openai/v1"  # provider "openai_compat": SF_LLM_BASE_URL overrides
# USD per million tokens, used ONLY for the cost estimate (cost_is_estimate = true). Update when prices change.
PRICE_TABLE_DATE = "2026-10"
PRICES = {"claude-sonnet-4-5": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0), "claude-opus-4-1": (15.0, 75.0), "claude-opus-4-6": (15.0, 75.0)}
KEEP_ENV = ("PATH", "LANG", "LC_ALL", "TMPDIR", "PYTHONHASHSEED", "AWS_LAMBDA_FUNCTION_NAME", "VERCEL", "VERCEL_ENV")

_bundle_cache: dict | None = None


def load_bundle() -> dict:
    global _bundle_cache
    if _bundle_cache is None:
        for cand in BUNDLE_CANDIDATES:
            if cand.is_file():
                _bundle_cache = json.loads(cand.read_text(encoding="utf-8"))
                break
        else:
            raise FileNotFoundError("runtime bundle not found (run `npm run ingest` in studio/ to generate api/py/bundle.json)")
    return _bundle_cache


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compat_price():
    """SF_LLM_PRICE_IN / SF_LLM_PRICE_OUT: USD per 1M tokens for the openai_compat model (enables cost estimates and budgets)."""
    try:
        i, o = os.environ.get("SF_LLM_PRICE_IN"), os.environ.get("SF_LLM_PRICE_OUT")
        return (float(i), float(o)) if i is not None and o is not None else None
    except ValueError:
        return None


def price_for(model: str):
    for key, p in PRICES.items():
        if key in model or model in key:
            return p
    return None


# ------------------------------------------------------------------ materialisation

def materialise(bundle: dict, root: Path) -> int:
    n = 0
    for rel, text in bundle.items():
        if ".." in rel or rel.startswith("/"):
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        n += 1
    return n


def _flow(obj) -> str:
    """One manifest item as a flow map the repo's skillmeta parser reads back (JSON is a valid subset)."""
    return json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))


def render_skill_md(slug: str, manifest: dict) -> str:
    """An authored manifest → SKILL.md with the metadata.agent block run_skill.py executes."""
    agent_inputs = [{k: v for k, v in i.items() if k in ("name", "type", "required", "from", "default", "flag") and v not in (None, "")}
                    for i in manifest.get("inputs", [])]
    steps = []
    for s in manifest.get("run", []):
        st = {k: v for k, v in s.items() if v not in (None, "", [])}
        steps.append(st)
    outputs = [{"path": o.get("path", ""), "checks": o.get("checks", [])} for o in manifest.get("outputs", [])]
    desc = (manifest.get("purpose") or slug).replace("\n", " ").strip()
    lines = ["---", f"name: {slug}", f"description: {json.dumps(desc, ensure_ascii=False)}", "metadata:",
             "  version: \"1\"", "  author: skills-factory", "  agent:", "    inputs:"]
    lines += [f"      - {_flow(i)}" for i in agent_inputs]
    lines.append("    run:")
    lines += [f"      - {_flow(s)}" for s in steps]
    lines.append("    outputs:")
    lines += [f"      - {_flow(o)}" for o in outputs]
    lines.append("---")
    body = manifest.get("instructions_md") or f"# {slug}\n"
    return "\n".join(lines) + "\n" + body.rstrip("\n") + "\n"


def write_authored(repo: Path, slug: str, manifest: dict, files: list) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,78}", slug or ""):
        raise ValueError("bad slug")
    sdir = repo / "skills" / "authored" / slug
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "SKILL.md").write_text(render_skill_md(slug, manifest), encoding="utf-8")
    for f in files or []:
        rel = str(f.get("path", ""))
        if not re.fullmatch(r"(scripts|assets|references)/[A-Za-z0-9._/-]{1,200}", rel) or ".." in rel:
            raise ValueError(f"bad file path: {rel}")
        dest = sdir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(str(f.get("content", "")), encoding="utf-8")
    # round-trip: what the runner will read must equal what the manifest declares
    sys.path.insert(0, str(repo / "scripts"))
    try:
        import skillmeta  # noqa: PLC0415
        agent = skillmeta.agent_block(skillmeta.load_skill(sdir)) or {}
    finally:
        sys.path.pop(0)
    want = [i.get("name") for i in manifest.get("inputs", [])]
    got = [i.get("name") for i in agent.get("inputs", [])]
    if want != got or len(agent.get("run", [])) != len(manifest.get("run", [])) or len(agent.get("outputs", [])) != len(manifest.get("outputs", [])):
        raise ValueError(f"manifest could not be rendered for the runner (inputs {got} != {want})")
    return sdir


# ------------------------------------------------------------------ LLM callback (stdlib, usage captured)

class Usage:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.retries = 0
        self.model = None

    def as_dict(self):
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "calls": self.calls, "retries": self.retries,
                "source": "provider-reported" if self.calls else None}


def make_anthropic_callback(key: str, usage: Usage, max_retries: int, max_tokens_cfg: int | None = None, temperature_cfg: float | None = None):
    def call(system, user, model, max_tokens, temperature):
        max_tokens = max_tokens_cfg or max_tokens
        temperature = temperature_cfg if temperature_cfg is not None else temperature
        body = json.dumps({"model": model, "max_tokens": int(max_tokens), "temperature": float(temperature), "system": system,
                           "messages": [{"role": "user", "content": user}]}).encode("utf-8")
        attempt = 0
        while True:
            req = urllib.request.Request(ANTHROPIC_URL, data=body, method="POST", headers={
                "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
            try:
                with urllib.request.urlopen(req, timeout=50) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
                except Exception:  # noqa: BLE001
                    pass
                if e.code in (429, 500, 502, 503, 529) and attempt < max_retries:
                    attempt += 1
                    usage.retries += 1
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise RuntimeError(f"anthropic HTTP {e.code}: {detail or e.reason}") from None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < max_retries:
                    attempt += 1
                    usage.retries += 1
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise RuntimeError(f"anthropic request failed: {e}") from None
        u = data.get("usage") or {}
        usage.calls += 1
        usage.input_tokens += int(u.get("input_tokens") or 0)
        usage.output_tokens += int(u.get("output_tokens") or 0)
        usage.model = data.get("model") or model
        text = "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
        if not text.strip():
            raise RuntimeError(f"anthropic returned no text (stop_reason={data.get('stop_reason')}); raise model_config.max_tokens if it is max_tokens")
        return text
    return call


def make_openai_compat_callback(base_url: str, key: str, usage: Usage, max_retries: int, max_tokens_cfg: int | None = None, temperature_cfg: float | None = None):
    """Any OpenAI-compatible /chat/completions endpoint (Groq, OpenRouter, vLLM, Ollama gateway…)."""
    url = base_url.rstrip("/") + "/chat/completions"
    def call(system, user, model, max_tokens, temperature):
        max_tokens = max_tokens_cfg or max_tokens
        temperature = temperature_cfg if temperature_cfg is not None else temperature
        payload = {"model": model, "max_completion_tokens": int(max_tokens), "temperature": float(temperature),
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        # Reasoning models spend completion tokens thinking before answering. Default to "low" on OpenAI (the call is
        # retried without it if the model rejects the parameter); SF_LLM_REASONING_EFFORT overrides ("none" disables).
        effort = os.environ.get("SF_LLM_REASONING_EFFORT", "").strip() or ("low" if "api.openai.com" in url else "")
        effort = "" if effort == "none" else effort
        if effort:
            payload["reasoning_effort"] = effort
        attempt = 0
        while True:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "content-type": "application/json", "authorization": f"Bearer {key}", "user-agent": "skills-factory/1"})
            try:
                with urllib.request.urlopen(req, timeout=50) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    err = json.loads(e.read().decode("utf-8")).get("error", {})
                    detail = err.get("message", "") if isinstance(err, dict) else str(err)
                except Exception:  # noqa: BLE001
                    pass
                # Parameter dialects differ: newer OpenAI models reject a custom temperature; some gateways only know
                # max_tokens. Adjust once per parameter and retry (not counted as a provider retry).
                low = (detail or "").lower()
                if e.code == 400 and "temperature" in low and "temperature" in payload:
                    payload.pop("temperature")
                    continue
                if e.code == 400 and "reasoning_effort" in low and "reasoning_effort" in payload:
                    payload.pop("reasoning_effort")
                    continue
                if e.code == 400 and "max_completion_tokens" in low and "max_completion_tokens" in payload:
                    payload["max_tokens"] = payload.pop("max_completion_tokens")
                    continue
                if e.code in (429, 500, 502, 503) and attempt < max_retries:
                    attempt += 1
                    usage.retries += 1
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise RuntimeError(f"openai_compat HTTP {e.code}: {detail or e.reason}") from None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < max_retries:
                    attempt += 1
                    usage.retries += 1
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise RuntimeError(f"openai_compat request failed: {e}") from None
        u = data.get("usage") or {}
        usage.calls += 1
        usage.input_tokens += int(u.get("prompt_tokens") or 0)
        usage.output_tokens += int(u.get("completion_tokens") or 0)
        usage.model = data.get("model") or model
        choices = data.get("choices") or []
        text = (choices[0].get("message", {}).get("content") or "") if choices else ""
        if not text.strip():
            reason = choices[0].get("finish_reason") if choices else "no choices"
            raise RuntimeError(f"openai_compat returned no text (finish_reason={reason}); "
                               + ("the token budget was used up before any answer — raise model_config.max_tokens or set SF_LLM_REASONING_EFFORT=low"
                                  if reason == "length" else "empty completion"))
        return text
    return call


# ------------------------------------------------------------------ execution

class SfTimeout(BaseException):
    """BaseException so the runner's own `except Exception` blocks cannot swallow the deadline."""


@contextlib.contextmanager
def scrubbed_env(work: Path):
    saved = dict(os.environ)
    try:
        os.environ.clear()
        for k in KEEP_ENV:
            if k in saved:
                os.environ[k] = saved[k]
        os.environ["HOME"] = str(work)
        os.environ["TMPDIR"] = str(work / "tmp")
        os.environ["RUN_SKILL_INPROC"] = "1"
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def fresh_runner(repo: Path):
    """Import run_skill & friends from THIS run's repo copy (a warm instance may have another path loaded)."""
    for m in ("run_skill", "check_output", "skillmeta", "behavioral_evals"):
        sys.modules.pop(m, None)
    sys.path.insert(0, str(repo / "scripts"))
    run_skill = importlib.import_module("run_skill")
    behavioral_evals = importlib.import_module("behavioral_evals")
    return run_skill, behavioral_evals


def run_with_deadline(fn, timeout_s: int):
    """Run fn() under a deadline. Returns (result, timed_out)."""
    if threading.current_thread() is threading.main_thread() and hasattr(signal, "SIGALRM"):
        state = {"timed_out": False}
        def on_alarm(signum, frame):  # noqa: ARG001
            # the in-process step runner catches BaseException and marks the step failed, so keep firing every
            # second until main() unwinds: every later step dies at once and the deadline stays hard
            state["timed_out"] = True
            signal.alarm(1)
            raise SfTimeout()
        old = signal.signal(signal.SIGALRM, on_alarm)
        signal.alarm(max(1, int(timeout_s)))
        try:
            r = fn()
            return r, state["timed_out"]
        except SfTimeout:
            return None, True
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
    box = {}
    def target():
        try:
            box["r"] = fn()
        except BaseException as e:  # noqa: BLE001
            box["e"] = e
    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return None, True
    if "e" in box:
        raise box["e"]
    return box.get("r"), False


def collect_outputs(out: Path):
    files, logs = [], []
    for p in sorted(out.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(out).as_posix()
        if rel in ("run.json", "needs_input.json"):
            continue
        raw = p.read_bytes()
        if rel.startswith("logs/"):
            logs.append(f"── {rel}\n{raw.decode('utf-8', errors='replace').rstrip()}\n")
            continue
        if len(files) >= MAX_OUTPUT_FILES:
            continue
        text = None
        if len(raw) <= MAX_CONTENT_TEXT:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = None
        files.append({"path": rel, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "content_text": text})
    return files, "".join(logs)


def execute(req: dict) -> dict:
    t_start = time.time()
    run_id = re.sub(r"[^A-Za-z0-9-]", "", str(req.get("run_id") or "")) or f"run-{int(t_start * 1000)}"
    timeout_s = min(MAX_TIMEOUT_S, max(1, int(req.get("timeout_s") or 50)))
    max_retries = min(2, max(0, int(req.get("max_retries") or 0)))
    provider_req = str(req.get("provider") or "none")
    model = str(req.get("model") or "claude-sonnet-4-5")
    work = WORK_ROOT / run_id
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    repo, out, inputs_dir = work / "repo", work / "out", work / "inputs"
    for d in (repo, out, inputs_dir, work / "tmp"):
        d.mkdir(parents=True, exist_ok=True)
    result = {"run_id": run_id, "status": "failed", "exit_code": None, "run_json": None, "needs_input": None, "outputs": [], "logs": "",
              "provider": {"requested": provider_req, "used": "none", "available": False, "note": ""},
              "model": None, "usage": None, "cost": {"usd": None, "is_estimate": True, "basis": None},
              "duration_ms": 0, "timed_out": False, "case_checks": None, "error": None,
              "runtime": {"python": sys.version.split()[0], "runtime_version": RUNTIME_VERSION, "runner_version": RUNNER_VERSION}}
    usage = Usage()
    try:
        bundle = load_bundle()
        materialise(bundle, repo)
        skill = req.get("skill") or {}
        if skill.get("kind") == "repo":
            repo_skill = str(skill.get("repo_skill") or "")
            if not re.fullmatch(r"[a-z0-9-]+/[a-z0-9-]+", repo_skill) or f"skills/{repo_skill}/SKILL.md" not in bundle:
                raise ValueError(f"unknown repo skill: {repo_skill}")
            skill_arg, skill_dir = repo_skill, repo / "skills" / repo_skill
        elif skill.get("kind") == "authored":
            skill_dir = write_authored(repo, str(skill.get("slug") or ""), skill.get("manifest") or {}, skill.get("files") or [])
            skill_arg = f"authored/{skill.get('slug')}"
        else:
            raise ValueError("skill.kind must be repo or authored")

        argv = [skill_arg]
        for name, v in (req.get("inputs") or {}).items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) or not isinstance(v, dict):
                raise ValueError(f"bad input: {name}")
            kind = v.get("kind")
            if kind == "text":
                ext = re.sub(r"[^a-z0-9]", "", str(v.get("ext") or "txt").lower())[:8] or "txt"
                p = inputs_dir / f"{name}.{ext}"
                p.write_text(str(v.get("content", "")), encoding="utf-8")
                argv += ["--input", f"{name}={p}"]
            elif kind == "fixture":
                rel = str(v.get("path", ""))
                if ".." in rel or not rel.startswith("evals/fixtures/"):
                    raise ValueError(f"bad fixture path: {rel}")
                p = skill_dir / rel
                if not p.exists():
                    raise ValueError(f"fixture not found: {rel}")
                argv += ["--input", f"{name}={p}"]
            elif kind == "value":
                val = str(v.get("value", ""))
                if val.startswith("{out}") or val == "":
                    pass
                elif "{" in val and "}" in val:
                    raise ValueError(f"input {name}: template tokens are not allowed in values")
                if val != "":
                    argv += ["--input", f"{name}={val}"]
            else:
                raise ValueError(f"bad input kind for {name}: {kind}")
        for name, val in (req.get("assumptions") or {}).items():
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) and str(val) != "":
                argv += ["--assume", f"{name}={val}"]

        callback = None
        budget = max(256, min(int(req.get("max_tokens") or 4000), 64000))  # manifest model_config.max_tokens, clamped
        temp = float(req["temperature"]) if req.get("temperature") is not None else None
        if provider_req == "anthropic":
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if key:
                provider_arg, callback = "jsbridge", make_anthropic_callback(key, usage, max_retries, budget, temp)
                result["provider"].update({"used": "anthropic", "available": True, "note": "ANTHROPIC_API_KEY present on the server"})
            else:
                provider_arg = "none"
                result["provider"].update({"used": "none", "available": False, "note": "provider unavailable — set ANTHROPIC_API_KEY on the server; llm steps were skipped"})
        elif provider_req == "openai_compat":
            key = os.environ.get("SF_LLM_API_KEY", "")
            base = os.environ.get("SF_LLM_BASE_URL") or DEFAULT_COMPAT_BASE_URL
            if key:
                provider_arg, callback = "jsbridge", make_openai_compat_callback(base, key, usage, max_retries, budget, temp)
                result["provider"].update({"used": "openai_compat", "available": True, "note": f"OpenAI-compatible endpoint {base}"})
            else:
                provider_arg = "none"
                result["provider"].update({"used": "none", "available": False, "note": "provider unavailable — set SF_LLM_API_KEY on the server; llm steps were skipped"})
        else:
            provider_arg = "none"
            result["provider"].update({"used": "none", "available": True, "note": "no model requested (provider: none)"})
        argv += ["--out", str(out), "--provider", provider_arg, "--model", model, "--inproc"]
        result["model"] = model if provider_arg == "jsbridge" else None

        captured = io.StringIO()
        with scrubbed_env(work):
            run_skill, behavioral_evals = fresh_runner(repo)
            behavioral_evals.JS_LLM_CALLBACK = callback
            saved_argv, saved_cwd = sys.argv, os.getcwd()
            def go():
                sys.argv = ["run_skill.py"] + argv
                os.chdir(str(work))
                with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                    try:
                        return int(run_skill.main() or 0)
                    except SystemExit as e:  # argparse / resolve_skill_dir
                        if isinstance(e.code, int):
                            return e.code
                        print(e.code, file=sys.stderr)
                        return 3
            try:
                code, timed_out = run_with_deadline(go, timeout_s)
            finally:
                behavioral_evals.JS_LLM_CALLBACK = None
                sys.argv = saved_argv
                os.chdir(saved_cwd)
                if sys.path and sys.path[0] == str(repo / "scripts"):
                    sys.path.pop(0)
        result["exit_code"] = code
        result["timed_out"] = timed_out
        rj = out / "run.json"
        if rj.is_file():
            try:
                result["run_json"] = json.loads(rj.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                result["run_json"] = None
        ni = out / "needs_input.json"
        if ni.is_file():
            try:
                result["needs_input"] = json.loads(ni.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        files, logs = collect_outputs(out)
        result["outputs"] = files
        result["logs"] = (captured.getvalue().rstrip() + ("\n" if captured.getvalue().strip() else "") + logs)[:400_000]
        if timed_out:
            result["status"] = "timeout"
            result["error"] = f"deadline of {timeout_s}s exceeded"
        elif result["needs_input"] is not None or code == 2:
            result["status"] = "needs_input"
            missing = [m.get("name") for m in (result["needs_input"] or {}).get("missing", [])]
            result["error"] = "missing required input(s): " + ", ".join(str(m) for m in missing)
        elif result["run_json"] is not None:
            ok = bool(result["run_json"].get("ok"))
            result["status"] = "succeeded" if ok else "failed"
            if not ok:
                bad_steps = [s for s in result["run_json"].get("steps", []) if not s.get("ok")]
                bad_checks = [c for c in result["run_json"].get("checks", []) if not c.get("pass")]
                result["error"] = f"{len(bad_steps)} step(s) not ok, {len(bad_checks)} check(s) failed"
        else:
            result["status"] = "failed"
            result["error"] = f"runner exited {code} without writing run.json"
        checks = req.get("checks")
        if isinstance(checks, list) and checks:
            try:
                result["case_checks"] = behavioral_evals.eval_case_checks(checks, int(code or 0), out, skill_dir)
            except Exception as e:  # noqa: BLE001
                result["case_checks"] = [{"check": str(c), "pass": False, "evidence": f"check could not run: {e}"} for c in checks]
    except Exception as e:  # noqa: BLE001
        result["status"] = "failed"
        result["error"] = f"{type(e).__name__}: {e}"[:1000]
    finally:
        result["usage"] = usage.as_dict() if usage.calls else None
        if usage.calls:
            result["model"] = usage.model or model
            env_price = compat_price() if result["provider"]["used"] == "openai_compat" else None
            p = env_price or price_for(usage.model or model)
            if p:
                basis = "provider-reported tokens × SF_LLM_PRICE_IN/OUT" if env_price else f"provider-reported tokens × price table {PRICE_TABLE_DATE} (api/py/run.py)"
                result["cost"] = {"usd": round((usage.input_tokens * p[0] + usage.output_tokens * p[1]) / 1_000_000, 6), "is_estimate": True,
                                  "basis": f"{basis}; not a billing figure"}
            else:
                result["cost"] = {"usd": None, "is_estimate": True, "basis": f"no price for model {usage.model or model} in the table"}
        result["duration_ms"] = int((time.time() - t_start) * 1000)
        shutil.rmtree(work, ignore_errors=True)
    return result


# ------------------------------------------------------------------ HTTP handler (Vercel)

def _authorised(headers) -> tuple[bool, int, str]:
    secret = os.environ.get("SF_RUNTIME_SECRET", "")
    if not secret:
        return False, 503, "runtime not configured: set SF_RUNTIME_SECRET on the server"
    given = headers.get("x-sf-runtime-secret", "")
    if not given or not hmac.compare_digest(given.encode(), secret.encode()):
        return False, 401, "unauthorised"
    return True, 200, ""


class handler(BaseHTTPRequestHandler):  # noqa: N801 (Vercel requires this name)
    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        ok, code, msg = _authorised(self.headers)
        if not ok:
            return self._json(code, {"error": msg})
        try:
            n = len(load_bundle())
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"error": str(e)})
        return self._json(200, {"ok": True, "python": sys.version.split()[0], "bundle_files": n,
                                "anthropic_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")), "compat_key_present": bool(os.environ.get("SF_LLM_API_KEY")),
                                "runtime_version": RUNTIME_VERSION, "runner_version": RUNNER_VERSION, "max_timeout_s": MAX_TIMEOUT_S})

    def do_POST(self):  # noqa: N802
        ok, code, msg = _authorised(self.headers)
        if not ok:
            return self._json(code, {"error": msg})
        try:
            n = int(self.headers.get("content-length") or 0)
            req = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception as e:  # noqa: BLE001
            return self._json(400, {"error": f"bad JSON body: {e}"})
        if not isinstance(req, dict):
            return self._json(400, {"error": "body must be a JSON object"})
        return self._json(200, execute(req))

    def log_message(self, *args):  # quiet: Vercel captures stdout anyway
        pass
