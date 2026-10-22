#!/usr/bin/env python3
"""Behavioral evals for giri-skills: trigger accuracy + with/without quality lift.

Modes:
  trigger  - does each eval prompt route to the right skill? (+ negative-set FP rate)
  quality  - do outputs produced WITH the skill beat outputs produced WITHOUT it?
  all      - both
  agent    - does running the skill (scripts/run_skill.py) produce the deliverables and
             pass its checks? Deterministic; --provider dry by default. Writes agent.csv
             and adds `agent pass` / Works|Partial|Broken columns to scorecard.md.

Providers: anthropic | openai | dry (canned responses; for CI and no-key runs).
API keys are read from the environment only (ANTHROPIC_API_KEY / OPENAI_API_KEY)
and are never printed, logged, or written to results.

Run: python3 scripts/behavioral_evals.py all --provider dry --out evals/results/dry
"""
from __future__ import annotations

import argparse
import csv
import datetime
import fnmatch
import json
import os
import random
import re
import sys
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
SHARED_DIR = ROOT / "shared"
RESULTS_DIR = ROOT / "evals" / "results"
JUDGE_PROMPT_PATH = ROOT / "evals" / "judge-prompt.md"
NEGATIVE_SET_PATH = ROOT / "evals" / "negative-set.json"

# --- Cost model: USD per 1M tokens (input, output). Estimates, not a bill. ---
PRICES = {
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-4-6": (15.0, 75.0),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4.1-nano": (0.1, 0.4),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
}
DEFAULT_PRICE = PRICES["claude-sonnet-4-5"]

KEY_REDACT = re.compile(r"sk-ant-[A-Za-z0-9_\-]+")


def redact(text: str) -> str:
    """Redact anything that looks like an Anthropic API key."""
    return KEY_REDACT.sub("[REDACTED]", text)


def frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    fm = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


# ---------------------------------------------------------------- providers

class LLM:
    name = "base"

    def complete(self, system: str, user: str, temperature: float = 1.0,
                 max_tokens: int = 1500) -> str:
        raise NotImplementedError


class DryLLM(LLM):
    """Canned provider: no network, no key. Exercises the full pipeline."""

    name = "dry"

    def complete(self, system: str, user: str, temperature: float = 1.0,
                 max_tokens: int = 1500) -> str:
        if "EVAL_JUDGE" in system:
            n = len(re.findall(r"(?m)^\d+\.", user))
            n = max(n, 1)
            return "\n".join(f"{i}. PASS - dry run (canned)" for i in range(1, n + 1))
        if "SKILL_ROUTER" in system:
            return "none"
        return "Dry-run output (canned). No real model was called."


def _retry(fn, attempts: int = 3):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - retry on any provider error
            last = e
            time.sleep(2 ** i)
    raise last


class AnthropicLLM(LLM):
    name = "anthropic"

    def __init__(self, model: str):
        try:
            import anthropic
        except ImportError:
            sys.exit("error: the 'anthropic' package is not installed "
                     "(pip install anthropic)")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("error: ANTHROPIC_API_KEY is not set in the environment")
        self.client = anthropic.Anthropic()
        self.model = model

    def complete(self, system: str, user: str, temperature: float = 1.0,
                 max_tokens: int = 1500) -> str:
        def _call():
            msg = self.client.messages.create(
                model=self.model, max_tokens=max_tokens, temperature=temperature,
                system=system, messages=[{"role": "user", "content": user}])
            return msg.content[0].text
        return _retry(_call)


class OpenAILLM(LLM):
    name = "openai"

    def __init__(self, model: str):
        try:
            import openai
        except ImportError:
            sys.exit("error: the 'openai' package is not installed "
                     "(pip install openai)")
        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("error: OPENAI_API_KEY is not set in the environment")
        self.client = openai.OpenAI()
        self.model = model

    def complete(self, system: str, user: str, temperature: float = 1.0,
                 max_tokens: int = 1500) -> str:
        def _call():
            resp = self.client.chat.completions.create(
                model=self.model, temperature=temperature, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
            return resp.choices[0].message.content
        return _retry(_call)


class NoLLM(LLM):
    """No model at all: run_skill.py skips llm steps with a recorded reason (used when no key)."""

    name = "none"

    def complete(self, system: str, user: str, temperature: float = 1.0,
                 max_tokens: int = 1500) -> str:
        raise RuntimeError("no provider key (LLM step not run)")


# Set by the host (e.g. the browser via Pyodide) to a callable
# (system, user, model, max_tokens, temperature) -> str. Never set from this file.
JS_LLM_CALLBACK = None


class JsBridgeLLM(LLM):
    """Routes completions to a host-registered callback (behavioral_evals.JS_LLM_CALLBACK).

    The browser registers a JS function that POSTs to the model API with a key held only in
    page memory; this process never sees the key. No callback -> "no provider key" error, so
    the runner marks the llm step skipped and its outputs' checks fail honestly.
    """

    name = "jsbridge"

    def __init__(self, model: str):
        self.model = model

    def complete(self, system: str, user: str, temperature: float = 1.0,
                 max_tokens: int = 1500) -> str:
        cb = JS_LLM_CALLBACK
        if cb is None:
            raise RuntimeError("no provider key (no JS_LLM_CALLBACK registered)")
        text = cb(system, user, self.model, max_tokens, temperature)
        return str(text)


def make_provider(name: str, model: str) -> LLM:
    if name == "dry":
        return DryLLM()
    if name == "none":
        return NoLLM()
    if name == "anthropic":
        return AnthropicLLM(model)
    if name == "openai":
        return OpenAILLM(model)
    if name == "jsbridge":
        return JsBridgeLLM(model)
    sys.exit(f"error: unknown provider '{name}' (anthropic|openai|dry|none|jsbridge)")


# ---------------------------------------------------------------- data loading

def load_skills():
    skills = []
    for md in sorted(SKILLS_DIR.rglob("SKILL.md")):
        rel = md.relative_to(SKILLS_DIR)
        if len(rel.parts) != 3:  # only skills/<domain>/<skill>/SKILL.md
            continue
        text = md.read_text(encoding="utf-8")
        fm = frontmatter(text)
        skill_dir = md.parent
        evals_path = skill_dir / "evals" / "evals.json"
        cases = []
        if evals_path.exists():
            try:
                cases = json.loads(evals_path.read_text(encoding="utf-8")).get("cases", [])
            except Exception:
                cases = []
        skills.append({
            "key": f"{rel.parts[0]}/{rel.parts[1]}",
            "domain": rel.parts[0],
            "name": fm.get("name", ""),
            "description": fm.get("description", ""),
            "dir": skill_dir,
            "md": text,
            "cases": cases,
        })
    return skills


def filter_skills(skills, globs):
    out = []
    for s in skills:
        rel = f"skills/{s['key']}"
        if any(fnmatch.fnmatch(rel, g) for g in globs):
            out.append(s)
    return out


def split_cases(skills):
    """Separate well-formed cases from malformed ones (never graded)."""
    ok, broken = [], []
    for s in skills:
        for c in s["cases"]:
            cid = c.get("id", "<no-id>")
            if not c.get("prompt") or not isinstance(c.get("expected"), list) \
                    or not c["expected"]:
                broken.append((s["key"], cid, "missing prompt or non-empty expected[]"))
            else:
                ok.append((s, c))
    return ok, broken


# ---------------------------------------------------------------- verdict (docs/EVAL-METHOD.md)

TRIGGER_MIN = 0.8        # routing: share of the skill's prompts the router sends to it
LIFT_MIN = 0.2           # absolute lift: pass rate with the skill minus without
GAIN_MIN = 0.5           # normalised gain: lift / (1 - without), the share of the remaining headroom the skill closes
WITH_MIN_FOR_GAIN = 0.8  # ... counted only when the with-skill pass rate is itself high


def quality_ok(without: float | None, with_: float | None) -> bool:
    """A skill's instructions help when the with-skill pass rate beats the baseline by LIFT_MIN, or, when the baseline
    is already high (a ceiling), when it closes at least GAIN_MIN of the remaining headroom and reaches WITH_MIN_FOR_GAIN.
    Normalised gain (Hake 1998) is the standard pre/post effect measure near a ceiling. A skill never passes by
    making things worse, nor without a measured improvement (with <= without)."""
    if without is None or with_ is None:
        return False
    lift = with_ - without
    if lift <= 0:            # no measured improvement is no evidence the instructions help, even at a ceiling
        return False
    if lift >= LIFT_MIN - 1e-9:
        return True
    headroom = 1.0 - without
    gain = 1.0 if headroom <= 1e-9 else lift / headroom
    return with_ >= WITH_MIN_FOR_GAIN - 1e-9 and gain >= GAIN_MIN - 1e-9


def skill_verdict(trigger_acc: float | None, without: float | None, with_: float | None) -> str:
    if trigger_acc is None or without is None or with_ is None:
        return "N/A"
    ok_t, ok_l = trigger_acc >= TRIGGER_MIN - 1e-9, quality_ok(without, with_)
    if ok_t and ok_l:
        return "OK"
    if not ok_t and not ok_l:
        return "BOTH"
    return "DESC" if not ok_t else "BODY"


# ---------------------------------------------------------------- confidence (docs/EVAL-FINDINGS.md)

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20261021      # fixed, so the same rows always give the same interval


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion (routing accuracy)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - h), min(1.0, c + h))


def lift_interval(quality_rows: list[dict]) -> tuple[float, float] | None:
    """95% percentile bootstrap interval for lift, resampling cases (the unit of independence: a case's expected items
    and runs move together). quality_rows: dicts with case_id, mode ('with'|'without'), pass ('PASS'|...)."""
    import random
    per: dict[str, list[int]] = {}
    for r in quality_rows:
        a = per.setdefault(r["case_id"], [0, 0, 0, 0])          # with pass, with n, without pass, without n
        i = 0 if r["mode"] == "with" else 2
        a[i] += r["pass"] == "PASS"
        a[i + 1] += 1
    cases = [v for v in per.values() if v[1] and v[3]]
    if len(cases) < 2:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    lifts = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        pick = [cases[rng.randrange(len(cases))] for _ in cases]
        wp, wn, op, on = (sum(c[j] for c in pick) for j in range(4))
        lifts.append(wp / wn - op / on)
    lifts.sort()
    return (lifts[int(0.025 * len(lifts))], lifts[int(0.975 * len(lifts)) - 1])


def skill_confidence(trigger_hits: list[bool], quality_rows: list[dict]) -> dict:
    """Point verdict plus 95% intervals; 'borderline' when an interval spans the bar, i.e. the verdict could flip on a
    re-run. Without/with come from the same rows as the point estimate."""
    k, n = sum(trigger_hits), len(trigger_hits)
    t_lo, t_hi = wilson_interval(k, n)
    wo = [r["pass"] == "PASS" for r in quality_rows if r["mode"] == "without"]
    wi = [r["pass"] == "PASS" for r in quality_rows if r["mode"] == "with"]
    without = sum(wo) / len(wo) if wo else None
    with_ = sum(wi) / len(wi) if wi else None
    li = lift_interval(quality_rows)
    trig_flip = n > 0 and (t_lo >= TRIGGER_MIN - 1e-9) != (t_hi >= TRIGGER_MIN - 1e-9)
    qual_flip = bool(li and without is not None and quality_ok(without, without + li[0]) != quality_ok(without, without + li[1]))
    return {"trigger_lo": t_lo, "trigger_hi": t_hi, "lift_lo": li[0] if li else None, "lift_hi": li[1] if li else None,
            "cases": len({r["case_id"] for r in quality_rows}), "confidence": "borderline" if (trig_flip or qual_flip) else "solid"}


CONFIDENCE_HEADER = ["skill", "trigger_lo", "trigger_hi", "lift_lo", "lift_hi", "cases", "confidence"]


def write_confidence(out_dir: Path, by_skill: dict[str, dict]) -> None:
    import csv as _csv
    with (out_dir / "confidence.csv").open("w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(CONFIDENCE_HEADER)
        fmt = lambda x: "" if x is None else f"{x:.3f}"
        for key in sorted(by_skill):
            c = by_skill[key]
            w.writerow([key, fmt(c["trigger_lo"]), fmt(c["trigger_hi"]), fmt(c["lift_lo"]), fmt(c["lift_hi"]), c["cases"], c["confidence"]])


# ---------------------------------------------------------------- case prompts with their inputs

ATTACH_FILE_CHARS = 6000     # per file
ATTACH_TOTAL_CHARS = 24000   # per case


def case_user_prompt(skill: dict, case: dict) -> str:
    """The user message for a quality/trigger call: the case prompt plus the inputs the case declares, rendered the
    way a user would supply them (pasted values; attached files shown in full up to a cap; folders as their files).
    Without this, a case whose inputs are files is graded on a prompt that never contains them."""
    inputs = case.get("inputs") or {}
    if not inputs:
        return case["prompt"]
    parts, used = [], 0
    for name, raw in inputs.items():
        v = str(raw)
        p = skill["dir"] / v if ("/" in v and not v.startswith("{")) else None
        files = []
        if p is not None and p.is_file():
            files = [(v, p)]
        elif p is not None and p.is_dir():
            files = [(f"{v}/{f.relative_to(p).as_posix()}", f) for f in sorted(p.rglob("*"))
                     if f.is_file() and "__pycache__" not in f.parts]
        if not files:
            parts.append(f"{name}: {v}")
            continue
        for label, f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                parts.append(f"{name} ({label}): [binary file, not shown]")
                continue
            room = max(0, min(ATTACH_FILE_CHARS, ATTACH_TOTAL_CHARS - used))
            shown = text[:room]
            used += len(shown)
            more = f"\n[... {len(text) - len(shown)} more characters not shown]" if len(shown) < len(text) else ""
            parts.append(f"{name} — attached file {label}:\n```\n{shown}\n```{more}")
    return case["prompt"] + "\n\nInputs supplied with this request:\n\n" + "\n\n".join(parts)


def load_negative_set():
    data = json.loads(NEGATIVE_SET_PATH.read_text(encoding="utf-8"))
    return data["prompts"]


# ---------------------------------------------------------------- prompt building

ROUTER_SYSTEM = """You are a SKILL_ROUTER. Given the list of available skills and a user \
request, select the single best skill.

Skills:
{skills}

Return exactly one skill name from the list above, or "none" if no skill fits \
the request. Output only the name, nothing else."""

JUDGE_SYSTEM = "You are an EVAL_JUDGE. Grade the output against each expected behavior."


def without_system() -> str:
    return ((SHARED_DIR / "quality-bar.md").read_text(encoding="utf-8") + "\n\n"
            + (SHARED_DIR / "writing-style.md").read_text(encoding="utf-8"))


def with_system(skill) -> str:
    parts = [without_system(),
             f"\n\n# Active skill: {skill['name']}\n",
             skill["md"],
             "\n\n## Available supporting files"]
    ref_dir = skill["dir"] / "references"
    refs = sorted(ref_dir.glob("*.md")) if ref_dir.is_dir() else []
    assets_dir = skill["dir"] / "assets"
    assets = sorted(p.name for p in assets_dir.iterdir()) if assets_dir.is_dir() else []
    parts.append("references: " + (", ".join(p.name for p in refs) or "(none)"))
    parts.append("assets: " + (", ".join(assets) or "(none)"))
    for p in refs:
        if p.stat().st_size <= 8 * 1024:
            parts.append(f"\n\n### references/{p.name}\n"
                         + p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def routing_target(skill: dict, case: dict) -> str:
    """The skill a case's prompt should route to: its own skill, or `routes_to` for a boundary case written to check
    that a neighbouring request goes elsewhere (counting those as misses penalised the skill for routing correctly)."""
    return str(case.get("routes_to") or skill["name"])


def parse_router(output: str, skills) -> str:
    token = output.strip().split()[0].strip("`\"'.,").lower() if output.strip() else "none"
    names = {s["name"].lower(): s["name"] for s in skills}
    if token == "none":
        return "none"
    return names.get(token, token)  # unknown token -> recorded as-is (counts wrong)


def parse_judge(raw: str, n: int):
    results = []
    for i in range(1, n + 1):
        m = re.search(rf"(?m)^{i}\.\s*(PASS|FAIL)\b\s*[-–:]\s*(.*)$", raw)
        if m:
            results.append((m.group(1) == "PASS", m.group(2).strip()[:200]))
        else:
            results.append((False, "unparseable judge line"))
    return results


# ---------------------------------------------------------------- cost guard

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def price_for(model: str):
    for key, price in PRICES.items():
        if key in model or model in key:
            return price
    print(f"warning: unknown model '{model}'; using claude-sonnet-4-5 pricing",
          file=sys.stderr)
    return DEFAULT_PRICE


def project_cost(calls, model: str):
    pin, pout = price_for(model)
    in_tok = sum(estimate_tokens(c["system"]) + estimate_tokens(c["user"]) for c in calls)
    out_tok = sum(c["max_tokens"] for c in calls)
    cost = (in_tok * pin + out_tok * pout) / 1_000_000
    return in_tok, out_tok, cost


# ---------------------------------------------------------------- agent mode

AGENT_HEADER = ["skill", "case_id", "check", "pass", "evidence"]
SCORECARD_COLS = ["skill", "trigger acc", "FP rate", "without", "with", "lift", "verdict",
                  "agent pass", "agent verdict"]


def agent_verdict(rate):
    if rate is None:
        return ""
    return "Works" if rate >= 0.9 else ("Partial" if rate >= 0.5 else "Broken")


def read_scorecard_rows(path: Path) -> dict:
    """Parse an existing scorecard table into {skill: {col: cell}} (blank when absent)."""
    rows = {}
    if not path.exists():
        return rows
    header = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set(cells[0]) <= {"-"}:
            continue
        rows[cells[0]] = dict(zip(header, cells))
    return rows


def eval_case_checks(checks, exit_code: int, out_dir: Path, skill_dir: Path):
    """Evaluate evals.json `checks`: 'exit:N', 'needs_input:<name>', 'exists:<file>'
    or {"file": <relpath>, "check": <spec>}."""
    import check_output  # local import: scripts/ is on sys.path via this file's dir
    results = []
    for c in checks:
        if isinstance(c, dict):
            spec, path = str(c.get("check", "")), out_dir / str(c.get("file", ""))
            # a reference file named by numbers_trace_to / cites_source_ids is a run output when it
            # exists in the case's out dir (e.g. "numbers_trace_to:estimate.json"); else skill-relative
            name, arg = check_output.parse_spec(spec)
            refs = arg if isinstance(arg, list) else [arg]
            cwd = out_dir if name in ("numbers_trace_to", "cites_source_ids") and arg and \
                all((out_dir / str(x)).is_file() for x in refs) else skill_dir
            r = check_output.run_check(spec, str(path), mode="real", exit_code=exit_code,
                                       out_dir=str(out_dir), cwd=str(cwd))
            r["check"] = f"{c.get('file')}: {spec}"
        else:
            name, _, arg = str(c).partition(":")
            if name == "exists":
                r = check_output.run_check("exists", str(out_dir / arg), out_dir=str(out_dir))
                r["check"] = str(c)
            else:
                r = check_output.run_check(str(c), None, exit_code=exit_code, out_dir=str(out_dir))
        results.append(r)
    return results


def agent_mode(args, skills) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import skillmeta
    out_dir = Path(args.out) if args.out else RESULTS_DIR / datetime.date.today().isoformat()
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    runner = Path(__file__).resolve().parent / "run_skill.py"
    rows, per_skill = [], {}
    n_cases = 0
    for s in skills:
        meta = skillmeta.load_skill(s["dir"])
        if not skillmeta.agent_block(meta):
            continue
        per_skill.setdefault(s["key"], [])
        for c in s["cases"]:
            if "inputs" not in c:
                continue
            n_cases += 1
            cid = c.get("id", f"case-{n_cases}")
            case_out = runs_dir / s["key"].replace("/", "__") / cid
            cmd = [sys.executable, "-I", str(runner), s["key"], "--provider", args.provider,
                   "--model", args.model, "--out", str(case_out)]
            for k, v in (c.get("inputs") or {}).items():
                v = str(v)
                if "/" in v and not v.startswith("{") and (s["dir"] / v).exists():
                    v = str(s["dir"] / v)
                cmd += ["--input", f"{k}={v}"]
            for k, v in (c.get("assume") or {}).items():
                cmd += ["--assume", f"{k}={v}"]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
            (case_out / "runner.log").parent.mkdir(parents=True, exist_ok=True)
            (case_out / "runner.log").write_text(redact(r.stdout + r.stderr), encoding="utf-8")
            checks = c.get("checks") or ["exit:0"]
            for res in eval_case_checks(checks, r.returncode, case_out, s["dir"]):
                rows.append([s["key"], cid, res["check"], "1" if res["pass"] else "0", res["evidence"]])
                per_skill[s["key"]].append(res["pass"])
    with (out_dir / "agent.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(AGENT_HEADER)
        w.writerows(rows)

    existing = read_scorecard_rows(out_dir / "scorecard.md")
    keys = sorted(set(existing) | {s["key"] for s in skills})
    domain_order = {"presales": 0, "build": 1, "ai-platform": 2, "career": 3}
    keys.sort(key=lambda k: (domain_order.get(k.split("/")[0], 9), k))
    lines = ["# Behavioral eval scorecard",
             f"_provider={args.provider} model={args.model} date={datetime.date.today().isoformat()}_",
             f"_agent mode: {n_cases} cases run with scripts/run_skill.py; verdict Works >= 0.9, "
             f"Partial >= 0.5, else Broken; blank = no agent cases_",
             "",
             "| " + " | ".join(SCORECARD_COLS) + " |",
             "|" + "---|" * len(SCORECARD_COLS)]
    for k in keys:
        prev = existing.get(k, {})
        passes = per_skill.get(k)
        rate = (sum(passes) / len(passes)) if passes else None
        cells = [prev.get(col, "") for col in SCORECARD_COLS[1:7]]
        cells += [f"{rate:.2f}" if rate is not None else "", agent_verdict(rate)]
        lines.append(f"| {k} | " + " | ".join(cells) + " |")
    (out_dir / "scorecard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    n_pass = sum(r[3] == "1" for r in rows)
    print(f"agent mode: {n_cases} cases, {n_pass}/{len(rows)} checks passed; "
          f"wrote {out_dir}/agent.csv, scorecard.md")
    return 0


# ---------------------------------------------------------------- main

def build_args():
    ap = argparse.ArgumentParser(description="Behavioral evals: trigger accuracy + quality lift")
    ap.add_argument("mode", choices=["trigger", "quality", "all", "agent"])
    ap.add_argument("--provider", default="dry", choices=["anthropic", "openai", "dry"])
    ap.add_argument("--model", default="claude-sonnet-4-5")
    ap.add_argument("--skills", action="append", default=None,
                    help="glob filter, repeatable (default: all skills)")
    ap.add_argument("--max-cases", type=int, default=0,
                    help="cap eval cases per skill (0 = no cap)")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--budget-usd", type=float, default=15.0)
    ap.add_argument("--yes", action="store_true",
                    help="proceed even if projected cost exceeds the budget")
    ap.add_argument("--out", default="",
                    help="results dir (default: evals/results/<YYYY-MM-DD>)")
    return ap.parse_args()


def main() -> int:
    args = build_args()
    rng = random.Random(args.seed)

    skills = filter_skills(load_skills(), args.skills or ["skills/*/*"])
    if not skills:
        sys.exit("error: --skills matched no skills")
    if args.mode == "agent":
        return agent_mode(args, skills)
    ok_cases, broken = split_cases(skills)
    if args.max_cases > 0:
        # shuffle per skill so the cap is a random (seeded) sample, not a prefix
        by_skill: dict[str, list] = {}
        for s, c in ok_cases:
            by_skill.setdefault(s["key"], []).append((s, c))
        ok_cases = []
        for lst in by_skill.values():
            rng.shuffle(lst)
            ok_cases.extend(lst[:args.max_cases])

    out_dir = Path(args.out) if args.out else RESULTS_DIR / datetime.date.today().isoformat()
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    router_sys = ROUTER_SYSTEM.format(
        skills="\n".join(f"- {s['name']}: {s['description']}" for s in skills))
    judge_template = JUDGE_PROMPT_PATH.read_text(encoding="utf-8")
    wout_sys = without_system()
    with_sys = {s["key"]: with_system(s) for s in skills}

    # ---- plan every LLM call up front so the cost guard sees the real prompts
    calls = []  # dicts: kind, skill, case_id, run, system, user, max_tokens, temperature
    do_trigger = args.mode in ("trigger", "all")
    do_quality = args.mode in ("quality", "all")
    if do_trigger:
        for run in range(1, args.runs + 1):
            for s, c in ok_cases:
                calls.append({"kind": "router", "skill": s["key"],
                              "case_id": c.get("id", ""), "run": run,
                              "system": router_sys, "user": case_user_prompt(s, c),
                              "max_tokens": 30, "temperature": 0})
        for i, prompt in enumerate(load_negative_set()):
            calls.append({"kind": "neg_router", "skill": "", "case_id": f"neg-{i+1:02d}",
                          "run": 1, "system": router_sys, "user": prompt,
                          "max_tokens": 30, "temperature": 0})
    if do_quality:
        for run in range(1, args.runs + 1):
            for s, c in ok_cases:
                for mode, sys_text in (("without", wout_sys),
                                       ("with", with_sys[s["key"]])):
                    calls.append({"kind": f"gen_{mode}", "skill": s["key"],
                                  "case_id": c.get("id", ""), "run": run,
                                  "system": sys_text, "user": case_user_prompt(s, c),
                                  "max_tokens": 1200, "temperature": 1.0})
                    # judge call follows the generation at runtime; its prompt
                    # depends on the output, so budget it with a typical size
                    calls.append({"kind": "judge", "skill": s["key"],
                                  "case_id": c.get("id", ""), "run": run,
                                  "system": JUDGE_SYSTEM,
                                  "user": judge_template,  # placeholder; real prompt built at runtime
                                  "max_tokens": 400, "temperature": 0,
                                  "judge_for": mode,
                                  "n_expected": len(c["expected"])})

    in_tok, out_tok, cost = project_cost(calls, args.model)
    print(f"Projected LLM usage: ~{len(calls)} calls, "
          f"~{in_tok//1000}k input + ~{out_tok//1000}k output tokens "
          f"~= ${cost:.2f} (model {args.model}, provider {args.provider})")
    print(f"Budget: ${args.budget_usd:.2f}")
    if cost > args.budget_usd and not args.yes:
        print(f"ABORTED: projected ${cost:.2f} exceeds budget "
              f"${args.budget_usd:.2f} (use --yes to override)", file=sys.stderr)
        return 1
    if args.provider == "dry":
        print("(dry provider: no real spend, no network, no key needed)")

    llm = make_provider(args.provider, args.model)
    raw_log = (raw_dir / "calls.jsonl").open("a", encoding="utf-8")

    def log_call(call, output):
        raw_log.write(json.dumps({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "mode": call["kind"], "skill": call["skill"],
            "case_id": call["case_id"], "run": call["run"],
            "system": call["system"][:4000], "user": call["user"][:4000],
            "output": redact(output)[:8000],
        }) + "\n")

    trigger_rows, quality_rows = [], []
    gen_cache = {}  # (skill, case_id, run, mode) -> output

    for call in calls:
        kind = call["kind"]
        if kind == "judge":
            # judge the generation this call was budgeted for
            gen_key = (call["skill"], call["case_id"], call["run"], call["judge_for"])
            output = gen_cache.get(gen_key, "")
            case = next(c for s, c in ok_cases
                        if s["key"] == call["skill"] and c.get("id") == call["case_id"])
            items = "\n".join(f"{i}. {e}" for i, e in enumerate(case["expected"], 1))
            user = judge_template.replace("{output}", output).replace("{expected_items}", items)
            out = llm.complete(call["system"], user,
                               temperature=0, max_tokens=call["max_tokens"])
            log_call({**call, "user": user}, out)
            for idx, (passed, evidence) in enumerate(parse_judge(out, call["n_expected"])):
                quality_rows.append([call["skill"], call["case_id"], call["run"],
                                     call["judge_for"], idx,
                                     "PASS" if passed else "FAIL", evidence])
            continue
        out = llm.complete(call["system"], call["user"],
                           temperature=call["temperature"],
                           max_tokens=call["max_tokens"])
        log_call(call, out)
        if kind in ("router", "neg_router"):
            selected = parse_router(out, skills)
            if kind == "router":
                owner = next(s for s in skills if s["key"] == call["skill"])
                case = next((c for c in owner["cases"] if c.get("id") == call["case_id"]), {})
                correct = "1" if selected == routing_target(owner, case) else "0"
                trigger_rows.append([call["skill"], call["case_id"], call["run"],
                                     selected, correct])
            else:
                trigger_rows.append(["(negative)", call["case_id"], call["run"],
                                     selected, ""])
        else:  # gen_without / gen_with
            gen_cache[(call["skill"], call["case_id"], call["run"],
                       kind.split("_", 1)[1])] = out
    raw_log.close()

    # ---- score
    stats = {}
    for s in skills:
        stats[s["key"]] = {"name": s["name"], "domain": s["domain"],
                           "trigger": [], "fp": 0,
                           "without": [], "with": []}
    for skill, _cid, _run, selected, correct in trigger_rows:
        if skill == "(negative)":
            for s in skills:
                if selected == s["name"]:
                    stats[s["key"]]["fp"] += 1
        else:
            stats[skill]["trigger"].append(correct == "1")
    n_neg = len(load_negative_set())
    for row in quality_rows:
        skill, _cid, _run, mode, _idx, passed, _ev = row
        stats[skill][mode].append(passed == "PASS")


    with (out_dir / "trigger.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["skill", "case_id", "run", "selected", "correct"])
        w.writerows(trigger_rows)
    with (out_dir / "quality.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["skill", "case_id", "run", "mode", "expected_idx", "pass", "evidence"])
        w.writerows(quality_rows)

    domain_order = {"presales": 0, "build": 1, "ai-platform": 2, "career": 3}
    lines = ["# Behavioral eval scorecard",
             f"_provider={args.provider} model={args.model} runs={args.runs} "
             f"seed={args.seed} date={datetime.date.today().isoformat()}_",
             f"_estimated spend: ${cost:.2f}_",
             "",
             "| skill | trigger acc | FP rate | without | with | lift | verdict |",
             "|---|---|---|---|---|---|---|"]
    for key in sorted(stats, key=lambda k: (domain_order.get(stats[k]["domain"], 9), k)):
        st = stats[key]
        t_acc = (sum(st["trigger"]) / len(st["trigger"])) if st["trigger"] else None
        fp = st["fp"] / n_neg if do_trigger else None
        wo = (sum(st["without"]) / len(st["without"])) if st["without"] else None
        wi = (sum(st["with"]) / len(st["with"])) if st["with"] else None
        lift = (wi - wo) if (wi is not None and wo is not None) else None
        v = skill_verdict(t_acc, wo, wi)
        fmt = lambda x: f"{x:.2f}" if x is not None else "n/a"
        lines.append(f"| {key} | {fmt(t_acc)} | {fmt(fp)} | {fmt(wo)} | "
                     f"{fmt(wi)} | {fmt(lift)} | {v} |")
    if broken:
        lines += ["", "## Broken cases (skipped, not graded)"]
        for skill, cid, reason in broken:
            lines += [f"- {skill} / {cid}: {reason}"]
    (out_dir / "scorecard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if do_quality:
        qdicts: dict[str, list[dict]] = {}
        for skill, cid, _run, mode, _idx, passed, _ev in quality_rows:
            qdicts.setdefault(skill, []).append({"case_id": cid, "mode": mode, "pass": passed})
        write_confidence(out_dir, {k: skill_confidence(stats[k]["trigger"], qdicts.get(k, [])) for k in stats})

    print(f"\nwrote {out_dir}/trigger.csv ({len(trigger_rows)} rows), "
          f"quality.csv ({len(quality_rows)} rows), scorecard.md, confidence.csv")
    if broken:
        print(f"skipped {len(broken)} broken case(s); see scorecard.md")
    print(f"estimated spend this run: ${cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
