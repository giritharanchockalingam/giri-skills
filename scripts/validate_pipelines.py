#!/usr/bin/env python3
"""Validate delivery pipeline templates (pipelines/*.json) against the library — docs/DELIVERY-PIPELINES.md.

    python3 scripts/validate_pipelines.py            # every pipelines/*.json and pipelines/composed/*.json
    python3 scripts/validate_pipelines.py FILE ...   # the given files

Rules (one message per violation, prefixed with the file):
  header      name matches the file, version, title, description, mode brownfield|greenfield, fits.stacks and
              fits.request_kinds lists, inputs typed (repo|string|text|json|md|csv|file|dir|path|flag) with unique
              names, stack_profile.detect is a script in the repo (and .after names a stage when present)
  stages      ids unique; adlc_stage in shared/adlc-stages.json; the role exists in roles/, its `stages` list
              includes the stage, and its `skills` include every skill the stage runs; >= 1 step; a gate
  steps       ids unique across the pipeline; kind skill|compose|agent|approval|pr; a skill step names an agent
              skill, uses only inputs the skill declares and supplies every required one; a compose step names a
              known derivation and declares outputs; an agent step names a known agent and existing constraint
              files, and `produces` (optional) is one of the file sets the executor can ask a builder for
              (["files.txt"] — the files step; ["plan.md", "tasks.csv"] — the plan-refine step);
              an approval step's role is the stage's role; a pr step has title, branch and body
  references  $in.<name> is a declared input; $profile.<key> is a stack-profile fact; $steps.<id>:<file>[#key]
              points to an EARLIER step and a file that step declares (a skill's {out}/ outputs, a compose
              step's outputs, diff.patch / agent-summary.md / files-changed.json for an agent step — or the files
              its `produces` lists, e.g. files.txt for the files step — pr.json for a pr step); `#key` reads a key of
              a .json file, `#csv` / `#lines` join the non-comment lines of a text file (comma / newline);
              $repo, $run.id, $run.state, $run.draft_only, $evidence are the executor's own values
  gates       kind output|exit|approval|all|any|external; output names a step of the stage, one of its declared
              files and a file-level check from scripts/check_output.py; exit names a skill step of the stage;
              approval names an approval step of the stage; all/any carry a non-empty `of`; external says `what`
  evidence    every entry is a valid $steps reference to this or an earlier stage
Exit 1 on any violation. Stdlib only. Importable: validate_pipeline(spec, ctx), load_context().
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import check_output  # noqa: E402
import skillmeta  # noqa: E402

INPUT_TYPES = {"repo", "string", "text", "json", "md", "csv", "file", "dir", "path", "flag"}
STEP_KINDS = {"skill", "compose", "agent", "approval", "pr"}
GATE_KINDS = {"output", "exit", "approval", "all", "any", "external"}
MODES = {"brownfield", "greenfield"}
DERIVATIONS = {"brief-from-request": ["brief.json"], "spec-from-prd": ["spec.md", "spec.json"],
               "feature-from-plan": ["feature.md", "feature.json"]}
AGENTS = {"claude-code"}
AGENT_OUTPUTS = ["diff.patch", "agent-summary.md", "files-changed.json"]
# what an agent step may declare under `produces` (the executor knows how to ask a builder for each set):
# the files step writes files.txt; the plan-refine step writes the refined plan.md + tasks.csv together; the
# prd-refine step writes the PRD with its acceptance criteria (the product manager's step)
AGENT_PRODUCE_SETS = [["files.txt"], ["plan.md", "tasks.csv"], ["prd-final.md"]]
# what each produce set needs as inputs (the code step — no `produces` — needs plan + target)
AGENT_NEEDS = {("prd-final.md",): ("prd",), ("plan.md", "tasks.csv"): ("plan", "target"), ("files.txt",): ("plan", "target")}
AGENT_PRODUCES = {f for s in AGENT_PRODUCE_SETS for f in s}
TEXT_MODIFIERS = {"csv", "lines"}       # $steps.<id>:<text file>#csv | #lines
PR_OUTPUTS = ["pr.json"]
APPROVAL_OUTPUTS = ["approval.json"]
PROFILE_KEYS = {"flavour", "framework", "package_manager", "test_runner", "e2e", "deploy_target", "migrations_dir",
                "monorepo_root", "baselines", "repo", "exists"}
PROFILE_BASELINES = {"nextjs", "perf", "ui", "debt"}
RUN_KEYS = {"id", "state", "draft_only"}
STEP_REF = re.compile(r"^\$steps\.([A-Za-z_][\w-]*):([^#]+?)(?:#([\w.\-\[\]]+))?$")
IN_REF = re.compile(r"^\$in\.([A-Za-z_][\w-]*)$")
PROFILE_REF = re.compile(r"^\$profile\.([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?$")
RUN_REF = re.compile(r"^\$run\.([A-Za-z_]\w*)$")


def load_context(root: Path = ROOT) -> dict:
    """Everything a pipeline is validated against: stage ids, roles, agent skills (declared inputs/outputs)."""
    tax = json.loads((root / "shared" / "adlc-stages.json").read_text(encoding="utf-8"))
    roles = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "roles").glob("*.json"))}
    skills = {}
    for md in sorted((root / "skills").glob("*/*/SKILL.md")):
        s = skillmeta.load_skill(md)
        a = skillmeta.agent_block(s)
        if not a:
            continue
        key = f"{md.parent.parent.name}/{md.parent.name}"
        outs = [str(o.get("path", "")) for o in (a.get("outputs") or []) if isinstance(o, dict)]
        skills[key] = {
            "inputs": {str(i["name"]): i for i in (a.get("inputs") or []) if isinstance(i, dict) and i.get("name")},
            "outputs": sorted({o[len("{out}/"):] for o in outs if o.startswith("{out}/")} | {"run.json"}),
        }
    return {"stages": {x["id"] for x in tax["stages"]}, "roles": roles, "skills": skills, "root": root}


def _ref_kind(value) -> str | None:
    return value if isinstance(value, str) and value.startswith("$") else None


def check_ref(value, inputs: set, known: dict, errors: list, where: str, allow_evidence: bool = False) -> None:
    """known: step id -> declared output files, for steps that ran EARLIER than the current one."""
    if _ref_kind(value) is None:
        return
    if value == "$repo" or (allow_evidence and value == "$evidence"):
        return
    m = IN_REF.match(value)
    if m:
        if m.group(1) not in inputs:
            errors.append(f"{where}: $in.{m.group(1)} is not a declared pipeline input")
        return
    m = RUN_REF.match(value)
    if m:
        if m.group(1) not in RUN_KEYS:
            errors.append(f"{where}: unknown run value {value} (one of {', '.join('$run.' + k for k in sorted(RUN_KEYS))})")
        return
    m = PROFILE_REF.match(value)
    if m:
        if m.group(1) not in PROFILE_KEYS:
            errors.append(f"{where}: unknown stack-profile key {value}")
        elif m.group(1) == "baselines" and m.group(2) not in PROFILE_BASELINES:
            errors.append(f"{where}: unknown baseline check {value} (one of {', '.join(sorted(PROFILE_BASELINES))})")
        return
    m = STEP_REF.match(value)
    if m:
        sid, rel, key = m.group(1), m.group(2), m.group(3)
        if sid not in known:
            errors.append(f"{where}: {value} references step '{sid}', which is not an earlier step")
        elif rel not in known[sid]:
            errors.append(f"{where}: {value} — step '{sid}' does not declare output '{rel}' (declares: {', '.join(known[sid]) or 'nothing'})")
        elif key and not rel.endswith(".json") and key not in TEXT_MODIFIERS:
            errors.append(f"{where}: {value} — '#{key}' on a text file must be one of {', '.join('#' + k for k in sorted(TEXT_MODIFIERS))} (a #key path reads a .json file)")
        elif key and rel.endswith(".json") and key in TEXT_MODIFIERS:
            errors.append(f"{where}: {value} — '#{key}' joins the lines of a text file, not a .json file")
        return
    errors.append(f"{where}: bad reference {value!r}")


def _validate_gate(gate, stage: dict, step_kinds: dict, step_outputs: dict, errors: list, where: str) -> None:
    if not isinstance(gate, dict):
        errors.append(f"{where}: gate must be an object"); return
    kind = gate.get("kind")
    if kind not in GATE_KINDS:
        errors.append(f"{where}: gate kind {kind!r} not in {sorted(GATE_KINDS)}"); return
    in_stage = {s.get("id") for s in stage.get("steps") or [] if isinstance(s, dict)}
    if kind in ("output", "exit", "approval"):
        sid = gate.get("step")
        if sid not in in_stage:
            errors.append(f"{where}: {kind} gate names step {sid!r}, not a step of this stage"); return
    if kind == "output":
        rel = gate.get("file")
        if not rel or rel not in step_outputs.get(gate["step"], []):
            errors.append(f"{where}: output gate file {rel!r} is not an output step '{gate['step']}' declares")
        name, _ = check_output.parse_spec(str(gate.get("check", "")))
        if name not in check_output.VOCAB or name in check_output.RUN_LEVEL:
            errors.append(f"{where}: output gate check {gate.get('check')!r} is not a file-level check of scripts/check_output.py")
    elif kind == "exit":
        if step_kinds.get(gate["step"]) != "skill":
            errors.append(f"{where}: exit gate must name a skill step (step '{gate['step']}' is {step_kinds.get(gate['step'])})")
    elif kind == "approval":
        if step_kinds.get(gate["step"]) != "approval":
            errors.append(f"{where}: approval gate must name an approval step (step '{gate['step']}' is {step_kinds.get(gate['step'])})")
    elif kind in ("all", "any"):
        of = gate.get("of")
        if not isinstance(of, list) or not of:
            errors.append(f"{where}: {kind} gate needs a non-empty `of` list"); return
        for i, g in enumerate(of):
            _validate_gate(g, stage, step_kinds, step_outputs, errors, f"{where}.of[{i}]")
    elif kind == "external":
        if not str(gate.get("what", "")).strip():
            errors.append(f"{where}: external gate must say `what` satisfies it")


def validate_pipeline(spec: dict, ctx: dict, filename: str | None = None) -> list[str]:
    e: list[str] = []
    if not isinstance(spec, dict):
        return ["pipeline must be a JSON object"]
    name = spec.get("name", "")
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", str(name)):
        e.append(f"name {name!r} must be a lowercase slug")
    if filename and Path(filename).stem != name:
        e.append(f"name {name!r} must match the file name {Path(filename).stem!r}")
    for k in ("version", "title", "description"):
        if not str(spec.get(k, "")).strip():
            e.append(f"missing '{k}'")
    if spec.get("mode") not in MODES:
        e.append(f"mode {spec.get('mode')!r} not in {sorted(MODES)}")
    fits = spec.get("fits")
    if not isinstance(fits, dict) or not isinstance(fits.get("stacks"), list) or not isinstance(fits.get("request_kinds"), list):
        e.append("fits must carry `stacks` and `request_kinds` lists")
    inputs: set[str] = set()
    for i, inp in enumerate(spec.get("inputs") or []):
        if not isinstance(inp, dict) or not inp.get("name"):
            e.append(f"inputs[{i}]: missing name"); continue
        if inp["name"] in inputs:
            e.append(f"inputs[{i}]: duplicate input name {inp['name']!r}")
        inputs.add(inp["name"])
        if inp.get("type") not in INPUT_TYPES:
            e.append(f"input '{inp['name']}': type {inp.get('type')!r} not in {sorted(INPUT_TYPES)}")
        if not isinstance(inp.get("required"), bool):
            e.append(f"input '{inp['name']}': `required` must be true or false")
    if not inputs:
        e.append("pipeline declares no inputs")
    sp = spec.get("stack_profile")
    stage_ids = [s.get("id") for s in spec.get("stages") or [] if isinstance(s, dict)]
    if not isinstance(sp, dict) or not sp.get("detect"):
        e.append("stack_profile.detect missing")
    else:
        if not (ctx["root"] / str(sp["detect"])).is_file():
            e.append(f"stack_profile.detect script missing: {sp['detect']}")
        if sp.get("after") and sp["after"] not in stage_ids:
            e.append(f"stack_profile.after names unknown stage {sp['after']!r}")
    stages = spec.get("stages")
    if not isinstance(stages, list) or not stages:
        e.append("stages must be a non-empty list"); return e

    known: dict[str, list[str]] = {}      # step id -> declared outputs (steps validated so far)
    step_kinds: dict[str, str] = {}
    seen_stage_ids: set[str] = set()
    for si, stage in enumerate(stages):
        if not isinstance(stage, dict) or not stage.get("id"):
            e.append(f"stages[{si}]: missing id"); continue
        sid = str(stage["id"])
        w = f"stage '{sid}'"
        if sid in seen_stage_ids:
            e.append(f"{w}: duplicate stage id")
        seen_stage_ids.add(sid)
        adlc = stage.get("adlc_stage")
        if adlc not in ctx["stages"]:
            e.append(f"{w}: adlc_stage {adlc!r} not in shared/adlc-stages.json")
        role_name = stage.get("role")
        role = ctx["roles"].get(role_name)
        if role is None:
            e.append(f"{w}: role {role_name!r} does not exist in roles/")
        elif adlc in ctx["stages"] and adlc not in (role.get("stages") or []):
            e.append(f"{w}: role '{role_name}' does not own stage '{adlc}' (its stages: {role.get('stages') or []})")
        steps = stage.get("steps")
        if not isinstance(steps, list) or not steps:
            e.append(f"{w}: no steps"); continue
        stage_outputs: dict[str, list[str]] = {}
        for ti, step in enumerate(steps):
            if not isinstance(step, dict) or not step.get("id"):
                e.append(f"{w}: steps[{ti}] missing id"); continue
            tid = str(step["id"])
            sw = f"{w} step '{tid}'"
            if tid in known:
                e.append(f"{sw}: duplicate step id (ids are unique across the pipeline)")
            kind = step.get("kind")
            if kind not in STEP_KINDS:
                e.append(f"{sw}: kind {kind!r} not in {sorted(STEP_KINDS)}")
                known[tid] = []; step_kinds[tid] = str(kind); continue
            outputs: list[str] = []
            if kind == "skill":
                skill = step.get("skill")
                meta = ctx["skills"].get(skill)
                if meta is None:
                    e.append(f"{sw}: skill {skill!r} is not an agent skill in skills/")
                else:
                    outputs = meta["outputs"]
                    if role is not None and skill not in (role.get("skills") or []):
                        e.append(f"{sw}: role '{role_name}' does not have skill '{skill}'")
                    given = step.get("inputs") or {}
                    for k in given:
                        if k not in meta["inputs"]:
                            e.append(f"{sw}: skill '{skill}' declares no input '{k}' (declares: {', '.join(meta['inputs']) or 'none'})")
                    for k, inp in meta["inputs"].items():
                        if inp.get("required") and k not in given:
                            e.append(f"{sw}: required input '{k}' of skill '{skill}' is not supplied")
                for k, v in (step.get("inputs") or {}).items():
                    check_ref(v, inputs, known, e, f"{sw} input '{k}'")
            elif kind == "compose":
                d = step.get("derive")
                if d not in DERIVATIONS:
                    e.append(f"{sw}: unknown derivation {d!r} (one of {', '.join(sorted(DERIVATIONS))})")
                outs = step.get("outputs")
                if not isinstance(outs, list) or not outs:
                    e.append(f"{sw}: compose step must declare `outputs`")
                elif d in DERIVATIONS and sorted(outs) != sorted(DERIVATIONS[d]):
                    e.append(f"{sw}: derivation '{d}' writes {DERIVATIONS[d]}, not {outs}")
                outputs = list(outs) if isinstance(outs, list) else []
                for k, v in (step.get("inputs") or {}).items():
                    check_ref(v, inputs, known, e, f"{sw} input '{k}'")
            elif kind == "agent":
                if step.get("agent") not in AGENTS:
                    e.append(f"{sw}: agent {step.get('agent')!r} not in {sorted(AGENTS)}")
                needs = AGENT_NEEDS.get(tuple(sorted(step.get("produces") or [])), ("plan", "target")) if step.get("produces") else ("plan", "target")
                for k in needs:
                    if k not in (step.get("inputs") or {}):
                        e.append(f"{sw}: agent step needs input '{k}'")
                for k, v in (step.get("inputs") or {}).items():
                    check_ref(v, inputs, known, e, f"{sw} input '{k}'")
                for c in step.get("constraints") or []:
                    if not (ctx["root"] / str(c)).is_file():
                        e.append(f"{sw}: constraint file missing: {c}")
                produces = step.get("produces")
                if produces is None:
                    outputs = list(AGENT_OUTPUTS)
                elif not isinstance(produces, list) or not produces or not all(isinstance(x, str) and x.strip() for x in produces):
                    e.append(f"{sw}: `produces` must be a non-empty list of file names")
                elif sorted(produces) not in [sorted(s) for s in AGENT_PRODUCE_SETS]:
                    e.append(f"{sw}: `produces` {produces} is not something the executor can ask a builder for (one of {AGENT_PRODUCE_SETS})")
                    outputs = list(produces)
                else:
                    outputs = list(produces)
            elif kind == "approval":
                if step.get("role") != role_name:
                    e.append(f"{sw}: approval role {step.get('role')!r} must be the stage's role '{role_name}'")
                outputs = list(APPROVAL_OUTPUTS)
            elif kind == "pr":
                for k in ("title", "branch", "body"):
                    if not str(step.get(k, "")).strip():
                        e.append(f"{sw}: pr step lacks '{k}'")
                for k in ("title", "body"):
                    check_ref(step.get(k), inputs, known, e, f"{sw} '{k}'", allow_evidence=True)
                outputs = list(PR_OUTPUTS)
            known[tid] = outputs
            step_kinds[tid] = kind
            stage_outputs[tid] = outputs
        if "gate" not in stage:
            e.append(f"{w}: no gate")
        else:
            _validate_gate(stage["gate"], stage, step_kinds, stage_outputs, e, f"{w} gate")
        ev = stage.get("evidence")
        if not isinstance(ev, list) or not ev:
            e.append(f"{w}: evidence must be a non-empty list of $steps references")
        else:
            for i, ref in enumerate(ev):
                if not STEP_REF.match(str(ref)):
                    e.append(f"{w} evidence[{i}]: {ref!r} is not a $steps.<id>:<file> reference")
                else:
                    check_ref(ref, inputs, known, e, f"{w} evidence[{i}]")
    for i, ref in enumerate(spec.get("outputs") or []):
        check_ref(ref, inputs, known, e, f"outputs[{i}]", allow_evidence=True)
    return e


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    files = [Path(a) for a in argv] or sorted((ROOT / "pipelines").glob("*.json")) + sorted((ROOT / "pipelines" / "composed").glob("*.json"))
    ctx = load_context()
    errors = []
    for f in files:
        try:
            spec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as ex:
            errors.append(f"{f}: cannot read JSON: {ex}"); continue
        errors += [f"{f.relative_to(ROOT) if f.is_relative_to(ROOT) else f}: {m}" for m in validate_pipeline(spec, ctx, f.name)]
    print(f"Checked {len(files)} pipeline(s), {len(errors)} errors")
    for m in errors:
        print("  -", m)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
