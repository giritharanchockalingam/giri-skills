#!/usr/bin/env python3
"""Run a skill as an agent: declared inputs -> script/llm steps -> checked outputs.

    python3 scripts/run_skill.py presales/effort-estimator \
        --input wbs=./wbs.csv --input rates=./rates.csv --input client=Acme \
        --out ./runs/acme --provider dry

    python3 scripts/run_skill.py --list              # agent skills and their inputs
    python3 scripts/run_skill.py --explain <skill>   # input contract in plain words
    python3 scripts/run_skill.py --demo <skill>      # run it on its own fixtures

The skill argument is `domain/name` or a path to the skill dir / SKILL.md.
Reads `metadata.agent` from SKILL.md (see docs/AGENT-REBUILD-PLAN.md §2):
  inputs:  [{name, type, required, from, default, copy, flag}]
           type: csv|json|md|txt|file|sql|dir (must exist) · path (may not exist yet)
                 string|args|flag (no file check; args is shell-split; flag -> {flag} when truthy)
  run:     [{step, kind: script|llm, ...}]
           script: cmd (python3 -> this interpreter with -I; `{name}`/`{out}`/`{skill_dir}`
                   substituted; `[... {opt} ...]` groups dropped when an optional input is
                   missing), stdout (file to capture), expect_exit (list, default [0]),
                   skip_if_missing (inputs)
           llm:    template, context (files), out, skip_if_missing
           any:    skip_if_present (inputs) — skip the step when one of them was supplied
  outputs: [{path, checks: [...]}]  — vocabulary in scripts/check_output.py

Exit codes: 0 all checks pass · 1 a step or check failed · 2 required input missing
(`{out}/needs_input.json` names it; `--assume name=value` proceeds with a labeled
assumption) · 3 not an agent skill / bad arguments.
Stdlib only. API keys are read by the provider from the environment and never written.

In-process mode (`--inproc` or RUN_SKILL_INPROC=1): script steps run via runpy in this
interpreter instead of a subprocess (same argv, cwd, stdout/stderr capture, exit codes,
`stdout:` redirection and `expect_exit`). Needed where subprocess does not exist
(Pyodide in the browser); outputs are byte-identical (tests/test_run_skill_inproc.py).
`--provider none` runs no LLM: llm steps are skipped with a recorded reason and their
checks fail honestly. `--provider jsbridge` routes LLM calls to a host-registered callback.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SKILLS = ROOT / "skills"
SHARED = ROOT / "shared"
sys.path.insert(0, str(HERE))
import check_output  # noqa: E402
import skillmeta  # noqa: E402

FILE_TYPES = {"csv", "json", "md", "txt", "file", "sql", "dir", "path"}
MUST_EXIST = FILE_TYPES - {"path"}
TOKEN_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
OPT_GROUP_RE = re.compile(r"\[([^\[\]]*\{[^\[\]]*)\]")
CONTEXT_LIMIT = 12 * 1024

LLM_INSTRUCTION = ("Fill this template using ONLY the context files. Where the files do not say, write "
                   "`[TO BE BASELINED — owner: <role>]` naming the accountable role (e.g. Client PMO, Delivery lead, "
                   "Account owner) — never leave the owner blank. Use one marker per unknown fact; drop empty example "
                   "rows instead of filling them with markers. Return the completed file only.")


# ------------------------------------------------------------------ discovery

def resolve_skill_dir(arg: str) -> Path:
    p = Path(arg)
    if p.is_file() and p.name == "SKILL.md":
        return p.parent.resolve()
    if p.is_dir() and (p / "SKILL.md").is_file():
        return p.resolve()
    cand = SKILLS / arg
    if (cand / "SKILL.md").is_file():
        return cand.resolve()
    sys.exit(f"error: skill not found: {arg} (use domain/name or a path)")


def skill_key(skill_dir: Path) -> str:
    try:
        rel = skill_dir.relative_to(SKILLS)
        return "/".join(rel.parts[:2])
    except ValueError:
        return skill_dir.name


def agent_skills():
    for md in sorted(SKILLS.rglob("SKILL.md")):
        if len(md.relative_to(SKILLS).parts) != 3:
            continue
        s = skillmeta.load_skill(md)
        if skillmeta.agent_block(s):
            yield s


def describe_inputs(agent: dict) -> list[str]:
    lines = []
    for i in agent.get("inputs", []):
        req = "required" if i.get("required") else "optional"
        extra = f" (default: {i['default']})" if i.get("default") not in (None, "") else ""
        src = f" — {i['from']}" if i.get("from") else ""
        lines.append(f"  --input {i['name']}=<{i.get('type', 'string')}>  [{req}]{extra}{src}")
    return lines


def cmd_list() -> int:
    skills = list(agent_skills())
    print(f"{len(skills)} agent skills")
    for s in skills:
        a = skillmeta.agent_block(s)
        print(f"\n{skill_key(s['dir'])}  v{s['metadata'].get('version', '?')}  "
              f"({len(a.get('run', []))} steps, {len(a.get('outputs', []))} outputs)")
        print("\n".join(describe_inputs(a)))
    return 0


def demo_args(arg: str) -> list[str]:
    """Translate --demo <skill> into a normal run using the skill's own happy-path eval fixtures."""
    skill_dir = resolve_skill_dir(arg)
    ev = skill_dir / "evals" / "evals.json"
    cases = json.loads(ev.read_text(encoding="utf-8")).get("cases", []) if ev.exists() else []
    case = next((c for c in cases if c.get("inputs") and "happy" in str(c.get("id", ""))), None) \
        or next((c for c in cases if c.get("inputs")), None)
    if not case:
        sys.exit(f"error: {arg} has no eval case with inputs to demo")
    argv = [skill_key(skill_dir)]
    for k, v in (case.get("inputs") or {}).items():
        v = str(v)
        if v.startswith("evals/"):
            v = str(skill_dir / v)
        argv += ["--input", f"{k}={v}"]
    for k, v in (case.get("assume") or {}).items():
        argv += ["--assume", f"{k}={v}"]
    print(f"demo: {skill_key(skill_dir)} on eval case '{case.get('id')}'", file=sys.stderr)
    return argv


def cmd_explain(arg: str) -> int:
    s = skillmeta.load_skill(resolve_skill_dir(arg))
    a = skillmeta.agent_block(s)
    if not a:
        print(f"{s['name']}: not an agent skill yet (no metadata.agent)")
        return 3
    print(f"# {s['name']} — how to run\n")
    print(s["description"].strip() + "\n")
    print("Inputs:")
    print("\n".join(describe_inputs(a)))
    print("\nSteps:")
    for st in a.get("run", []):
        if st.get("kind") == "llm":
            print(f"  {st['step']}: fill {st.get('template')} from {st.get('context', [])} -> {st.get('out')}")
        else:
            print(f"  {st['step']}: {st.get('cmd')}" + (f"  (stdout -> {st['stdout']})" if st.get("stdout") else ""))
    print("\nOutputs and checks:")
    for o in a.get("outputs", []):
        print(f"  {o['path']}: {', '.join(str(c) for c in o.get('checks', []))}")
    print("\nMissing a required input? The runner exits 2 and writes needs_input.json. "
          "Use --assume name=value to proceed with a labeled assumption.")
    return 0


# ------------------------------------------------------------------ inputs

def parse_kv(items, label):
    out = {}
    for it in items or []:
        if "=" not in it:
            sys.exit(f"error: {label} expects name=value, got {it!r}")
        k, _, v = it.partition("=")
        out[k.strip()] = v
    return out


def resolve_inputs(agent, given: dict, assumed: dict, out_dir: Path, skill_dir: Path):
    """Return (values, assumptions, missing). values[name] is '' for absent optional inputs."""
    values, assumptions, missing = {}, {}, []
    declared = agent.get("inputs", [])
    names = {i["name"] for i in declared}
    for k in list(given) + list(assumed):
        if k not in names:
            sys.exit(f"error: unknown input '{k}'; declared inputs: {sorted(names)}")
    for spec in declared:
        name, typ = spec["name"], str(spec.get("type", "string"))
        raw = None
        if name in given:
            raw = given[name]
        elif name in assumed:
            raw = assumed[name]
            assumptions[name] = f"[ASSUMED: {name} = {assumed[name]}]"
        elif spec.get("default") not in (None, ""):
            raw = str(spec["default"])
            if typ in FILE_TYPES and not Path(raw).is_absolute():
                raw = str(skill_dir / raw)
        if raw is None or raw == "":
            if spec.get("required"):
                missing.append({"name": name, "type": typ, "from": spec.get("from", ""),
                                "question": f"Provide `{name}` ({typ}): {spec.get('from', '')}".strip()})
            values[name] = ""
            continue
        raw = raw.replace("{out}", str(out_dir)).replace("{skill_dir}", str(skill_dir))
        if typ in FILE_TYPES:
            p = Path(raw).expanduser()
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            if typ in MUST_EXIST and not p.exists():
                missing.append({"name": name, "type": typ, "from": spec.get("from", ""),
                                "question": f"`{name}` file not found: {p}"})
                values[name] = ""
                continue
            if spec.get("copy") and p.is_file():
                out_dir.mkdir(parents=True, exist_ok=True)
                dest = out_dir / p.name
                if dest.resolve() != p.resolve():
                    shutil.copy(p, dest)
                p = dest
            values[name] = str(p)
        elif typ == "flag":
            truthy = str(raw).strip().lower() in ("1", "true", "yes", "y", "on")
            values[name] = str(spec.get("flag", f"--{name.replace('_', '-')}")) if truthy else ""
        else:
            values[name] = str(raw)
    return values, assumptions, missing


# ------------------------------------------------------------------ substitution

def substitute(text: str, values: dict) -> str:
    def rep(m):
        return values.get(m.group(1), m.group(0))
    return TOKEN_RE.sub(rep, text)


def build_argv(cmd: str, values: dict, arg_types: dict) -> list[str]:
    """Tokenize the template first, then substitute, so paths with spaces stay one argument."""
    # drop optional groups whose inputs are all missing
    def drop(m):
        group = m.group(1)
        refs = TOKEN_RE.findall(group)
        if refs and any(values.get(r, "") == "" for r in refs):
            return ""
        return group
    cmd = OPT_GROUP_RE.sub(drop, cmd)
    argv = []
    for tok in shlex.split(cmd):
        m = TOKEN_RE.fullmatch(tok)
        if m and arg_types.get(m.group(1)) == "args":
            argv += shlex.split(values.get(m.group(1), ""))
        else:
            sub = substitute(tok, values)
            if sub != "" or not m:
                argv.append(sub)
    return check_output.python_argv(argv)


# ------------------------------------------------------------------ steps

def run_script_step(step, values, arg_types, skill_dir: Path, logs: Path) -> dict:
    argv = build_argv(str(step.get("cmd", "")), values, arg_types)
    t0 = time.time()
    try:
        code, out, err = check_output.run_command(argv, cwd=skill_dir, timeout=900)
    except Exception as e:  # noqa: BLE001
        code, out, err = 127, "", f"could not run: {e}"
    dur = round(time.time() - t0, 3)
    name = str(step["step"])
    (logs / f"{name}.stdout.txt").write_text(out, encoding="utf-8")
    (logs / f"{name}.stderr.txt").write_text(err, encoding="utf-8")
    expect = step.get("expect_exit", [0])
    expect = [int(x) for x in (expect if isinstance(expect, list) else [expect])]
    ok = code in expect
    if step.get("stdout") and (ok or out.strip()):
        dest = Path(substitute(str(step["stdout"]), values))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding="utf-8")
    return {"step": name, "kind": "script", "cmd": " ".join(shlex.quote(a) for a in argv),
            "exit": code, "expected_exit": expect, "ok": ok, "duration_s": dur,
            "log": str(logs / f"{name}.stderr.txt"),
            "error": "" if ok else (err.strip().splitlines() or [f"exit {code}"])[-1][:300]}


def run_llm_step(step, values, assumptions, skill_dir: Path, provider, logs: Path) -> dict:
    name = str(step["step"])
    template = skill_dir / str(step.get("template", ""))
    out_path = Path(substitute(str(step.get("out", "")), values))
    if not template.is_file():
        return {"step": name, "kind": "llm", "ok": False, "exit": 1, "duration_s": 0,
                "error": f"template missing: {template}"}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    tmpl = template.read_text(encoding="utf-8")
    if provider.name == "dry":
        out_path.write_text(tmpl.rstrip("\n") + "\n<!-- dry-run: template unfilled -->\n", encoding="utf-8")
        return {"step": name, "kind": "llm", "ok": True, "exit": 0, "provider": "dry",
                "duration_s": round(time.time() - t0, 3), "out": str(out_path), "error": ""}
    system = ((SHARED / "quality-bar.md").read_text(encoding="utf-8") + "\n\n"
              + (SHARED / "writing-style.md").read_text(encoding="utf-8"))
    parts = [LLM_INSTRUCTION, "", "## Template", "", tmpl]
    if assumptions:
        parts += ["", "## Assumptions supplied by the user (label each use as [ASSUMED: …])", ""]
        parts += [f"- {v}" for v in assumptions.values()]
    for ctx in step.get("context", []) or []:
        cp = Path(substitute(str(ctx), values))
        if not cp.is_absolute():
            cp = skill_dir / cp
        if not cp.is_file():
            parts += ["", f"## Context: {cp.name}", "", "(file missing)"]
            continue
        body = cp.read_text(encoding="utf-8", errors="replace")
        if len(body) > CONTEXT_LIMIT:
            body = body[:CONTEXT_LIMIT] + "\n[... truncated at 12 KB ...]"
        parts += ["", f"## Context: {cp.name}", "", body]
    user = "\n".join(parts)
    (logs / f"{name}.prompt.txt").write_text(user, encoding="utf-8")
    try:
        text = provider.complete(system, user, temperature=0.2, max_tokens=4000)
    except Exception as e:  # noqa: BLE001
        if "no provider key" in str(e):
            # --provider none, or jsbridge with no callback registered: the step did not run.
            # Its output is absent, so the checks on it fail honestly.
            reason = "no provider key (LLM step not run)"
            return {"step": name, "kind": "llm", "ok": False, "exit": 1, "provider": provider.name,
                    "skipped": True, "skipped_reason": reason, "reason": reason,
                    "duration_s": round(time.time() - t0, 3), "error": f"skipped: {reason}"}
        return {"step": name, "kind": "llm", "ok": False, "exit": 1,
                "duration_s": round(time.time() - t0, 3), "error": f"provider error: {e}"[:300]}
    text = re.sub(r"^```[a-z]*\n|\n```\s*$", "", text.strip())
    out_path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    return {"step": name, "kind": "llm", "ok": True, "exit": 0, "provider": provider.name,
            "duration_s": round(time.time() - t0, 3), "out": str(out_path), "error": ""}


# ------------------------------------------------------------------ main

def build_args():
    ap = argparse.ArgumentParser(description="Run a skill as an agent (inputs -> steps -> checked outputs)")
    ap.add_argument("skill", nargs="?", help="domain/name or path")
    ap.add_argument("--input", action="append", default=[], metavar="NAME=VALUE")
    ap.add_argument("--assume", action="append", default=[], metavar="NAME=VALUE",
                    help="supply a missing input as a labeled assumption")
    ap.add_argument("--out", default="", help="output dir (default: runs/<skill>-<timestamp>)")
    ap.add_argument("--provider", default="dry", choices=["dry", "anthropic", "openai", "jsbridge", "none"],
                    help="none = run no LLM: llm steps are skipped with a reason; jsbridge = host callback")
    ap.add_argument("--model", default="claude-sonnet-4-5")
    ap.add_argument("--inproc", action="store_true",
                    help="run script steps in this interpreter (runpy) instead of a subprocess")
    ap.add_argument("--list", action="store_true", help="list agent skills and their inputs")
    ap.add_argument("--explain", metavar="SKILL", help="print the input contract in plain words")
    ap.add_argument("--demo", metavar="SKILL", help="run the skill on its own happy-path eval fixtures")
    argv = sys.argv[1:]
    if "--demo" in argv:
        i = argv.index("--demo")
        argv = demo_args(argv[i + 1]) + argv[:i] + argv[i + 2:]
    return ap.parse_args(argv)


def main() -> int:
    args = build_args()
    if args.list:
        return cmd_list()
    if args.explain:
        return cmd_explain(args.explain)
    if not args.skill:
        sys.exit("error: give a skill (domain/name), --list or --explain")
    if args.inproc:
        os.environ["RUN_SKILL_INPROC"] = "1"

    skill_dir = resolve_skill_dir(args.skill)
    skill = skillmeta.load_skill(skill_dir)
    agent = skillmeta.agent_block(skill)
    if not agent:
        print(f"error: {skill['name']} is not an agent skill yet (no metadata.agent in SKILL.md)",
              file=sys.stderr)
        return 3
    out_dir = Path(args.out) if args.out else ROOT / "runs" / f"{skill['name']}-{int(time.time())}"
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    logs = out_dir / "logs"
    logs.mkdir(exist_ok=True)

    given = parse_kv(args.input, "--input")
    assumed = parse_kv(args.assume, "--assume")
    values, assumptions, missing = resolve_inputs(agent, given, assumed, out_dir, skill_dir)
    if missing:
        payload = {"skill": skill_key(skill_dir), "missing": missing,
                   "hint": "re-run with --input name=value, or --assume name=value to proceed with a labeled assumption"}
        (out_dir / "needs_input.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        for m in missing:
            print(f"needs input: {m['question']}", file=sys.stderr)
        print(f"wrote {out_dir / 'needs_input.json'}", file=sys.stderr)
        return 2

    values["out"] = str(out_dir)
    values["skill_dir"] = str(skill_dir)
    arg_types = {i["name"]: str(i.get("type", "string")) for i in agent.get("inputs", [])}

    sys.path.insert(0, str(HERE))
    from behavioral_evals import make_provider  # noqa: E402  (reuses the provider abstraction)
    provider = make_provider(args.provider, args.model)

    steps, halted = [], False
    for step in agent.get("run", []):
        skip = [s for s in (step.get("skip_if_missing") or []) if values.get(str(s), "") == ""]
        present = [s for s in (step.get("skip_if_present") or []) if values.get(str(s), "") != ""]
        if skip or present:
            reason = (f"missing optional input(s): {skip}" if skip else f"input(s) supplied: {present}")
            steps.append({"step": str(step["step"]), "kind": step.get("kind"), "ok": True,
                          "skipped": True, "reason": reason})
            continue
        if halted:
            steps.append({"step": str(step["step"]), "kind": step.get("kind"), "ok": False,
                          "skipped": True, "reason": "earlier step failed"})
            continue
        if step.get("kind") == "llm":
            res = run_llm_step(step, values, assumptions, skill_dir, provider, logs)
        else:
            res = run_script_step(step, values, arg_types, skill_dir, logs)
        steps.append(res)
        if not res["ok"]:
            halted = True

    mode = "dry" if args.provider == "dry" else "real"
    checks = []
    for o in agent.get("outputs", []):
        path = substitute(str(o.get("path", "")), values)
        for c in o.get("checks", []) or []:
            spec = substitute(str(c), values)
            r = check_output.run_check(spec, path, mode=mode, out_dir=str(out_dir), cwd=str(skill_dir))
            r["path"] = path
            checks.append(r)

    ok = all(s["ok"] for s in steps) and all(c["pass"] for c in checks)
    run = {"skill": skill_key(skill_dir), "version": str(skill["metadata"].get("version", "")),
           "provider": args.provider, "model": args.model if args.provider in ("anthropic", "openai", "jsbridge") else "",
           "out": str(out_dir),
           "inputs": {k: v for k, v in values.items() if k not in ("out", "skill_dir")},
           "assumptions": assumptions, "steps": steps, "checks": checks, "ok": ok}
    (out_dir / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    n_pass = sum(c["pass"] for c in checks)
    print(f"{run['skill']}: {'OK' if ok else 'FAILED'} — {len(steps)} steps, "
          f"{n_pass}/{len(checks)} checks passed; see {out_dir / 'run.json'}")
    for s in steps:
        if not s["ok"]:
            print(f"  step {s['step']} failed: {s.get('error') or s.get('reason')}")
    for c in checks:
        if not c["pass"]:
            print(f"  check {c['check']} on {Path(c['path']).name}: {c['evidence']}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # e.g. `--list | head`
        sys.exit(0)
