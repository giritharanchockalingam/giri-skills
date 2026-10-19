#!/usr/bin/env python3
"""Run a composed agent: skills chained by configuration, every step checked, one trace.

An agent is configuration, not code: `agents/<name>/agent.json` lists the agent's inputs, its config (model provider,
failure policy) and ordered steps. Three step kinds:

  skill     {"id", "skill": "domain/name", "inputs": {name: ref}, "assume": {name: text}, "continue_on_fail": bool,
             "gate": bool}
            Runs the skill with scripts/run_skill.py (its own declared inputs, scripts and output checks). A "gate" skill
            that exits 1 with its outputs written is a verdict ("blocked"), e.g. a release plan that says not ready.
  compose   {"id", "compose": {"out": "facts.csv", "format": "kv-csv" | "json", "rows": {key: ref}, "include": ref}}
            Builds the next skill's input from earlier outputs (deterministic; a missing value fails the step).
  approval  {"id", "approval": {"role": "Account owner", "note": "..."}}
            Pauses the agent until the named role approves (`--approve <id>`); exit 4 = awaiting approval.

References (`ref`): "$in.<name>" (agent input), "$steps.<id>:<file>" (a file an earlier step wrote),
"$steps.<id>:<file>#<dotted.key>" (a value inside an earlier JSON output); anything else is a literal.

Usage:
  python3 scripts/run_agent.py agents/presales-pursuit --input client=Acme --input wbs=path.csv ... --out runs/x
  python3 scripts/run_agent.py --demo presales-pursuit --provider none --out runs/x
  python3 scripts/run_agent.py --validate agents/presales-pursuit      (static checks, no run)
Exit codes: 0 ok · 1 a step failed (outputs and trace written) · 2 missing agent input · 3 invalid spec ·
4 awaiting approval · 5 blocked by a gate step (its verdict and outputs are complete). Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
AGENTS = ROOT / "agents"
sys.path.insert(0, str(HERE))
import skillmeta  # noqa: E402

REF_RE = re.compile(r"^\$(in)\.([A-Za-z_][\w-]*)$|^\$steps\.([A-Za-z_][\w-]*):([^#]+?)(?:#([\w.\-\[\]]+))?$")
ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
KINDS = ("skill", "compose", "approval")


# ------------------------------------------------------------------ spec

def resolve_agent_dir(arg: str) -> Path:
    p = Path(arg)
    for cand in (p, AGENTS / arg):
        if (cand / "agent.json").is_file():
            return cand.resolve()
        if cand.is_file() and cand.name == "agent.json":
            return cand.parent.resolve()
    sys.exit(f"error: no agent.json for '{arg}' (looked in {p} and {AGENTS / arg})")


def load_spec(agent_dir: Path) -> dict:
    return json.loads((agent_dir / "agent.json").read_text(encoding="utf-8"))


def step_kind(step: dict) -> str | None:
    found = [k for k in KINDS if k in step]
    return found[0] if len(found) == 1 else None


def skill_outputs(skill_id: str) -> set[str]:
    agent = skillmeta.agent_block(skillmeta.load_skill(ROOT / "skills" / skill_id)) or {}
    return {str(o.get("path", "")).replace("{out}/", "") for o in agent.get("outputs") or []}


def _refs(value) -> list[str]:
    if isinstance(value, str):
        return [value] if value.startswith("$") else []
    if isinstance(value, dict):
        return [r for v in value.values() for r in _refs(v)]
    if isinstance(value, list):
        return [r for v in value for r in _refs(v)]
    return []


def validate(spec: dict) -> list[str]:
    """Static checks: every problem is reported, none is fatal on its own."""
    problems: list[str] = []
    for key in ("name", "description", "steps"):
        if not spec.get(key):
            problems.append(f"missing '{key}'")
    agent_inputs = {str(i.get("name")): i for i in spec.get("inputs") or []}
    files_by_step: dict[str, set[str]] = {}
    seen: list[str] = []
    for n, step in enumerate(spec.get("steps") or [], 1):
        sid = str(step.get("id", ""))
        where = f"step {n} ({sid or '?'})"
        if not ID_RE.match(sid):
            problems.append(f"{where}: id must be lower-kebab-case")
        if sid in seen:
            problems.append(f"{where}: duplicate id")
        kind = step_kind(step)
        if kind is None:
            problems.append(f"{where}: needs exactly one of {KINDS}")
            seen.append(sid)
            continue
        for ref in _refs(step.get("inputs")) + _refs(step.get("compose")) + _refs(step.get("assume")):
            m = REF_RE.match(ref)
            if not m:
                problems.append(f"{where}: bad reference {ref!r}")
            elif m.group(1) == "in" and m.group(2) not in agent_inputs:
                problems.append(f"{where}: {ref} is not a declared agent input")
            elif m.group(3):
                if m.group(3) not in seen:
                    problems.append(f"{where}: {ref} refers to a step that does not run before it")
                elif files_by_step.get(m.group(3)) is not None and m.group(4) not in files_by_step[m.group(3)]:
                    problems.append(f"{where}: {ref} — step '{m.group(3)}' does not declare '{m.group(4)}' "
                                    f"(it declares {sorted(files_by_step[m.group(3)])})")
        if kind == "skill":
            skill_id = str(step["skill"])
            sdir = ROOT / "skills" / skill_id
            if not (sdir / "SKILL.md").is_file():
                problems.append(f"{where}: skill {skill_id} not found")
            else:
                agent = skillmeta.agent_block(skillmeta.load_skill(sdir))
                if not agent:
                    problems.append(f"{where}: {skill_id} is not an executable skill")
                else:
                    declared = {str(i["name"]): i for i in agent.get("inputs") or []}
                    mapped = set((step.get("inputs") or {}).keys()) | set((step.get("assume") or {}).keys())
                    for name in mapped - set(declared):
                        problems.append(f"{where}: {skill_id} has no input '{name}' (declares {sorted(declared)})")
                    for name, i in declared.items():
                        if i.get("required") and name not in mapped and not i.get("default"):
                            problems.append(f"{where}: required input '{name}' of {skill_id} is not mapped")
                    files_by_step[sid] = skill_outputs(skill_id)
        elif kind == "compose":
            c = step["compose"]
            if not c.get("out") or c.get("format") not in ("kv-csv", "json") or not isinstance(c.get("rows"), dict):
                problems.append(f"{where}: compose needs out, format kv-csv|json and rows{{}}")
            files_by_step[sid] = {str(c.get("out", ""))}
        elif kind == "approval":
            if not str((step["approval"] or {}).get("role", "")).strip():
                problems.append(f"{where}: approval needs a role")
            files_by_step[sid] = set()
        seen.append(sid)
    for ref in _refs(spec.get("outputs")):
        m = REF_RE.match(ref)
        if not m or (m.group(3) and m.group(3) not in seen):
            problems.append(f"outputs: bad reference {ref!r}")
    return problems


# ------------------------------------------------------------------ run-time references

class RefError(Exception):
    pass


def _dig(data, dotted: str):
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise RefError(f"key '{dotted}' not found")
    if isinstance(cur, (dict, list)):
        raise RefError(f"key '{dotted}' is not a single value")
    return cur


def resolve(value, inputs: dict, step_dirs: dict):
    """A ref → its value: agent input, a path written by an earlier step, or a value inside its JSON."""
    if not isinstance(value, str) or not value.startswith("$"):
        return value
    m = REF_RE.match(value)
    if not m:
        raise RefError(f"bad reference {value!r}")
    if m.group(1) == "in":
        if m.group(2) not in inputs:
            raise RefError(f"agent input '{m.group(2)}' not given")
        return inputs[m.group(2)]
    sid, rel, key = m.group(3), m.group(4), m.group(5)
    if sid not in step_dirs:
        raise RefError(f"step '{sid}' has not run")
    path = step_dirs[sid] / rel
    if not path.is_file():
        raise RefError(f"step '{sid}' did not write {rel}")
    if not key:
        return str(path)
    try:
        return _dig(json.loads(path.read_text(encoding="utf-8")), key)
    except json.JSONDecodeError as e:
        raise RefError(f"{rel} is not JSON: {e}") from None


# ------------------------------------------------------------------ steps

def run_skill(skill_id: str, args: list[str], out: Path, provider: str, model: str, inproc: bool) -> tuple[int, str]:
    argv = [skill_id, *args, "--out", str(out), "--provider", provider, "--model", model]
    if inproc:  # same interpreter (portal runtimes have no subprocess); fresh runner state per step
        import importlib
        import contextlib
        sys.modules.pop("run_skill", None)
        rs = importlib.import_module("run_skill")
        buf = io.StringIO()
        saved = sys.argv
        sys.argv = ["run_skill.py", *argv, "--inproc"]
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                try:
                    code = int(rs.main() or 0)
                except SystemExit as e:
                    code = e.code if isinstance(e.code, int) else 1
        finally:
            sys.argv = saved
        return code, buf.getvalue()
    r = subprocess.run([sys.executable, "-I", str(HERE / "run_skill.py"), *argv], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def do_compose(c: dict, inputs: dict, step_dirs: dict, out: Path) -> Path:
    rows = {k: resolve(v, inputs, step_dirs) for k, v in c["rows"].items()}
    target = out / str(c["out"])
    if c["format"] == "json":
        target.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        return target
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["key", "value", "source", "notes"])
    for k, v in rows.items():
        src = c["rows"][k]
        w.writerow([k, v, src if isinstance(src, str) and src.startswith("$") else "agent config", "composed by agent"])
    extra = c.get("include")
    if extra:  # owner-supplied rows the earlier steps cannot produce (e.g. owners, rollback time)
        path = Path(str(resolve(extra, inputs, step_dirs)))
        for row in csv.DictReader(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")):
            if row.get("key") and row["key"] not in rows:
                w.writerow([row["key"], row.get("value", ""), row.get("source", path.name), row.get("notes", "")])
    target.write_text(buf.getvalue(), encoding="utf-8")
    return target


def checks_of(run_json: Path) -> tuple[int, int, list[str]]:
    if not run_json.is_file():
        return 0, 0, []
    r = json.loads(run_json.read_text(encoding="utf-8"))
    checks = r.get("checks") or []
    failed = [f"{Path(c.get('path', '')).name}: {c.get('check')} — {c.get('evidence')}" for c in checks if not c.get("pass")]
    return sum(bool(c.get("pass")) for c in checks), len(checks), failed


def execute_step(n: int, step: dict, spec: dict, inputs: dict, step_dirs: dict, out: Path, provider: str, model: str,
                 inproc: bool, approved: set, approver: str = "") -> dict:
    """Run one step; record it; register its output dir in step_dirs. Shared by the CLI loop and the portal runtime
    (which executes one step per request and restores earlier steps' files into step_dirs first)."""
    kind, sid = step_kind(step), step["id"]
    sdir = out / "steps" / f"{n:02d}-{sid}"
    sdir.mkdir(parents=True, exist_ok=True)
    rec = {"id": sid, "kind": kind, "status": "ok"}
    t0 = time.time()
    try:
        if kind == "approval":
            ap_cfg = step["approval"]
            rec.update(role=ap_cfg["role"], note=ap_cfg.get("note", ""))
            if sid in approved:
                rec.update(status="approved", approver=approver or f"(role: {ap_cfg['role']})", at=time.strftime("%Y-%m-%dT%H:%M:%S"))
            else:
                rec["status"] = "awaiting_approval"
        elif kind == "compose":
            path = do_compose(step["compose"], inputs, step_dirs, sdir)
            rec["out"] = str(path)
        else:
            rec["skill"] = step["skill"]
            optional = {i["name"] for i in spec.get("inputs") or [] if not i.get("required")}
            args = []
            for k, v in (step.get("inputs") or {}).items():
                m = REF_RE.match(v) if isinstance(v, str) else None
                if m and m.group(1) == "in" and m.group(2) in optional and not str(inputs.get(m.group(2), "")).strip():
                    continue  # optional agent input not supplied: the skill applies its own rule (e.g. TBD with owner)
                args.append(f"--input={k}={resolve(v, inputs, step_dirs)}")
            args += [f"--assume={k}={v}" for k, v in (step.get("assume") or {}).items()]
            code, log = run_skill(step["skill"], args, sdir, step.get("provider", provider), step.get("model", model), inproc)
            (sdir / "agent-step.log").write_text(log, encoding="utf-8")
            passed, total, failed = checks_of(sdir / "run.json")
            rec.update(exit=code, checks_passed=passed, checks_total=total, out=str(sdir))
            if code == 2:
                rec.update(status="needs_input", error="skill reported a missing input — see needs_input.json")
            elif code != 0:
                tail = log.strip().splitlines()
                reason = next((ln.strip() for ln in tail if "step " in ln and "failed:" in ln), None) or (failed[0] if failed else (tail[-1] if tail else ""))
                # a gate step saying "no" (exit 1, outputs written) is a verdict, not a malfunction
                rec.update(status="blocked" if step.get("gate") and (sdir / "run.json").is_file() else "failed", error=reason[:240])
    except RefError as e:
        rec.update(status="failed", error=str(e))
    rec["duration_s"] = round(time.time() - t0, 3)
    step_dirs[sid] = sdir
    return rec


# ------------------------------------------------------------------ main

def demo_inputs(agent_dir: Path) -> dict:
    demo = json.loads((agent_dir / "demo.json").read_text(encoding="utf-8"))
    return {k: (str((ROOT / v).resolve()) if isinstance(v, str) and (ROOT / v).is_file() else v)
            for k, v in demo.get("inputs", {}).items()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a composed agent (skills chained by configuration)")
    ap.add_argument("agent", nargs="?", help="agents/<name> or <name>")
    ap.add_argument("--input", action="append", default=[], metavar="NAME=VALUE")
    ap.add_argument("--approve", action="append", default=[], metavar="STEP_ID", help="approve an approval step")
    ap.add_argument("--approver", default="", help="who approves (recorded in the trace)")
    ap.add_argument("--out", default="")
    ap.add_argument("--provider", default=None, choices=["dry", "anthropic", "openai", "jsbridge", "none"],
                    help="overrides config.provider")
    ap.add_argument("--model", default=None)
    ap.add_argument("--inproc", action="store_true", help="run skills in this interpreter")
    ap.add_argument("--validate", metavar="AGENT", help="static checks only")
    ap.add_argument("--demo", metavar="AGENT", help="run on agents/<name>/demo.json inputs")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for d in sorted(AGENTS.glob("*/agent.json")):
            s = json.loads(d.read_text(encoding="utf-8"))
            kinds = [step_kind(x) for x in s.get("steps", [])]
            print(f"{s['name']}: {kinds.count('skill')} skills, {kinds.count('approval')} approvals — {s['description']}")
        return 0
    if a.validate:
        agent_dir = resolve_agent_dir(a.validate)
        problems = validate(load_spec(agent_dir))
        print(f"{agent_dir.name}: {'valid' if not problems else f'{len(problems)} problem(s)'}")
        for p in problems:
            print(f"  - {p}")
        return 0 if not problems else 3

    agent_dir = resolve_agent_dir(a.demo or a.agent or sys.exit("error: give an agent, --demo, --validate or --list"))
    spec = load_spec(agent_dir)
    problems = validate(spec)
    if problems:
        print(f"invalid agent spec ({len(problems)}):", *problems, sep="\n  - ", file=sys.stderr)
        return 3
    inputs = demo_inputs(agent_dir) if a.demo else {}
    for kv in a.input:
        k, _, v = kv.partition("=")
        inputs[k.strip()] = v
    missing = [i["name"] for i in spec.get("inputs") or [] if i.get("required") and not str(inputs.get(i["name"], "")).strip()]
    cfg = spec.get("config") or {}
    # config.provider: "auto" = the deployment's configured model (portal); the CLI runs no model unless --provider is given
    provider = a.provider or ("none" if str(cfg.get("provider", "auto")) == "auto" else str(cfg.get("provider")))
    model = a.model or str(cfg.get("model") or "claude-sonnet-4-5")
    out = Path(a.out or ROOT / "runs" / f"agent-{spec['name']}-{int(time.time())}").expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    spec_sha = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    trace = {"agent": spec["name"], "version": spec.get("version", ""), "spec_sha256": spec_sha, "provider": provider,
             "model": model if provider not in ("none", "dry") else "", "inputs": inputs, "steps": [], "status": "running",
             "out": str(out)}

    def finish(status: str, code: int) -> int:
        trace["status"] = status
        outs = []
        for ref in spec.get("outputs") or []:
            try:
                outs.append(str(resolve(ref, inputs, step_dirs)))
            except RefError:
                pass
        trace["outputs"] = outs
        (out / "agent-run.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")
        ok_steps = sum(s["status"] in ("ok", "approved") for s in trace["steps"])
        print(f"{spec['name']}: {status.upper()} — {ok_steps}/{len(spec['steps'])} steps; trace {out / 'agent-run.json'}")
        for s in trace["steps"]:
            mark = {"ok": "✓", "approved": "✓", "failed": "✗", "blocked": "■", "awaiting_approval": "…", "needs_input": "?"}.get(s["status"], "·")
            extra = f" {s['checks_passed']}/{s['checks_total']} checks" if s.get("checks_total") else ""
            print(f"  {mark} {s['id']:<22} {s['kind']:<8} {s.get('skill', '')}{extra}"
                  + (f" — {s['error']}" if s.get("error") else ""))
        return code

    step_dirs: dict[str, Path] = {}
    if missing:
        (out / "needs_input.json").write_text(json.dumps({"agent": spec["name"], "missing": missing}, indent=2), encoding="utf-8")
        trace["missing_inputs"] = missing
        return finish("needs_input", 2)

    for n, step in enumerate(spec["steps"], 1):
        rec = execute_step(n, step, spec, inputs, step_dirs, out, provider, model, a.inproc, set(a.approve), a.approver)
        trace["steps"].append(rec)
        if rec["status"] == "awaiting_approval":
            (out / "awaiting_approval.json").write_text(json.dumps(
                {"agent": spec["name"], "step": rec["id"], "role": rec["role"], "note": rec.get("note", ""),
                 "resume": f"re-run with --approve {rec['id']}"}, indent=2), encoding="utf-8")
            return finish("awaiting_approval", 4)
        if rec["status"] == "blocked":
            return finish("blocked", 5)
        if rec["status"] in ("failed", "needs_input") and not step.get("continue_on_fail"):
            return finish("failed", 1)
    return finish("ok", 0)


if __name__ == "__main__":
    sys.exit(main())
