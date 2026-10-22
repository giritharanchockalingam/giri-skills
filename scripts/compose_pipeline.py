#!/usr/bin/env python3
"""Compose a delivery pipeline when no template fits — docs/DELIVERY-PIPELINES.md → When no template fits.

    python3 scripts/compose_pipeline.py --profile stack-profile.json --request-kind feature
        [--mode brownfield|greenfield] [--stages a,b,c] [--name NAME] [--out pipelines/composed/<name>.json] [--explain]
    python3 scripts/compose_pipeline.py --stacks nextjs,supabase --request-kind greenfield --out pipelines/composed/new-shop.json

Deterministic assembly, nothing invented:
  1. the request kind (shared/request-kinds.json) says which ADLC stages run, in order (`--stages` overrides);
  2. for each stage the role is the first in roles/ (sorted by file name) whose `stages` lists it — none: error;
  3. the stage's steps come from the STEP LIBRARY below — the exact wiring the shipped templates use — restricted
     to skills the role lists; a skill is chosen when its `metadata.fits` matches the stack (signal ids derived
     from the stack profile, `any` matches all) and the request kind, and every step it needs is in the pipeline;
  4. compose steps (brief-from-request, spec-from-prd, feature-from-plan) are added where first needed; the agent
     files step (produces files.txt) and build step take the plan, else the composed spec; a stage with no fitting
     skill is dropped with a note.
`--explain` prints the decision table (stage → role → step: chosen / rejected / dropped and why). The result passes
scripts/validate_pipelines.py and runs with scripts/deliver.py. Exit 2 on a bad argument or an unknown kind, 1 when
nothing could be composed. Stdlib only. Importable: compose(...), stacks_from_profile(...), load_catalog(...).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import skillmeta  # noqa: E402

KINDS_FILE = ROOT / "shared" / "request-kinds.json"
VERSION = "0.1.0"
NOTE = "Approve the plan before any code is written; edit plan.md / tasks.csv in the step folder first if files or tests are missing"

# ------------------------------------------------------------------ the step library (the templates' wiring)
# Per ADLC stage, in order. A step is included when: kind skill → the stage's role lists the skill, its fits match,
# every `requires` step is present; kind compose → something later requires it (added where first needed); kind
# agent → its plan resolves (plan.md, else spec.md); kind approval / pr → the step it follows is present.
# `inputs` values that reference an absent step are dropped when the input is in `optional`; otherwise the step
# cannot be wired. `gate` is the step's contribution to the stage gate; `evidence` the files it records.
LIBRARY: dict[str, list[dict]] = {
    "bootstrap": [
        {"id": "scaffold", "kind": "skill", "skill": "build/project-bootstrap", "inputs": {"target": "$repo", "name": "$in.name"},
         "gate": {"kind": "output", "step": "scaffold", "file": "bootstrap-report.json", "check": "json"},
         "evidence": ["$steps.scaffold:bootstrap-report.json"]},
    ],
    "requirements": [
        {"id": "brief", "kind": "compose", "derive": "brief-from-request", "inputs": {"request": "$in.request", "brief": "$in.brief"},
         "outputs": ["brief.json"], "evidence": ["$steps.brief:brief.json"]},
        {"id": "prd", "kind": "skill", "skill": "build/product-spec-prd", "requires": ["brief"],
         "inputs": {"brief": "$steps.brief:brief.json", "draft_only": "$run.draft_only"},
         "gate": {"kind": "output", "step": "prd", "file": "prd-final.md", "check": "sections:[\"Acceptance criteria\"]"},
         "evidence": ["$steps.prd:prd-final.md"]},
    ],
    "architecture": [
        {"id": "spec", "kind": "compose", "derive": "spec-from-prd", "requires": ["brief"], "optional": ["prd"],
         "inputs": {"brief": "$steps.brief:brief.json", "prd": "$steps.prd:prd-final.md", "request": "$in.request"},
         "outputs": ["spec.md", "spec.json"]},
        {"id": "plan", "kind": "skill", "skill": "build/spec-to-plan", "requires": ["spec"],
         "inputs": {"spec": "$steps.spec:spec.md", "section": "$steps.spec:spec.json#section", "repo": "$repo"},
         "evidence": ["$steps.plan:plan.md", "$steps.plan:tasks.csv"]},
        {"id": "plan-approval", "kind": "approval", "requires": ["plan"], "note": NOTE,
         "gate": {"kind": "approval", "step": "plan-approval"}},
    ],
    "build": [
        {"id": "feature", "kind": "compose", "derive": "feature-from-plan", "requires": ["plan"], "optional": ["brief"],
         "inputs": {"plan": "$steps.plan:plan.md", "tasks": "$steps.plan:tasks.csv", "brief": "$steps.brief:brief.json"},
         "outputs": ["feature.md", "feature.json"]},
        {"id": "files", "kind": "agent", "agent": "claude-code", "produces": ["files.txt"], "optional": ["tasks"],
         "inputs": {"plan": "$steps.plan:plan.md", "tasks": "$steps.plan:tasks.csv", "target": "$repo"},
         "plan_fallback": ["$steps.plan:plan.md", "$steps.spec:spec.md"],
         "evidence": ["$steps.files:files.txt"]},
        {"id": "tests", "kind": "skill", "skill": "build/test-strategy-tdd", "requires": ["feature", "files"],
         "inputs": {"feature": "$steps.feature:feature.md", "files": "$steps.files:files.txt#csv", "target": "$repo"},
         "evidence": ["$steps.tests:test-plan.md", "$steps.tests:scaffold-report.json"]},
        {"id": "code", "kind": "agent", "agent": "claude-code", "optional": ["tests", "files"],
         "inputs": {"plan": "$steps.plan:plan.md", "tests": "$steps.tests:test-plan.md", "files": "$steps.files:files.txt", "target": "$repo"},
         "plan_fallback": ["$steps.plan:plan.md", "$steps.spec:spec.md"],
         "constraints": ["skills/build/nextjs-enterprise-conventions/SKILL.md", "shared/stack-conventions.md"],
         "fallback_gate": {"kind": "output", "step": "code", "file": "diff.patch", "check": "exists"},
         "evidence": ["$steps.code:diff.patch", "$steps.code:agent-summary.md"]},
        {"id": "conventions", "kind": "skill", "skill": "build/nextjs-enterprise-conventions", "step_gate": True,
         "inputs": {"target": "$repo", "baseline": "$profile.baselines.nextjs"},
         "gate": {"kind": "exit", "step": "conventions"}, "evidence": ["$steps.conventions:report.md"]},
    ],
    "evaluate": [
        {"id": "review", "kind": "skill", "skill": "build/code-review-runner", "requires": ["code"], "optional": ["prd"],
         "inputs": {"diff": "$steps.code:diff.patch", "spec": "$steps.prd:prd-final.md"},
         "gate": {"kind": "output", "step": "review", "file": "review.md", "check": "contains:\"Verdict: **PASS**\""},
         "evidence": ["$steps.review:review.md"]},
        {"id": "security", "kind": "skill", "skill": "build/security-review", "requires": ["code"],
         "inputs": {"diff": "$steps.code:diff.patch", "target": "$repo", "draft_only": "$run.draft_only"},
         "gate": {"kind": "exit", "step": "security"}, "evidence": ["$steps.security:security-review.md"]},
        {"id": "perf", "kind": "skill", "skill": "build/perf-review-runner",
         "inputs": {"target": "$repo", "baseline": "$profile.baselines.perf"},
         "gate": {"kind": "exit", "step": "perf"}, "evidence": ["$steps.perf:report.md"]},
        {"id": "ui", "kind": "skill", "skill": "build/ui-component-quality",
         "inputs": {"target": "$repo", "baseline": "$profile.baselines.ui"},
         "gate": {"kind": "exit", "step": "ui"}, "evidence": ["$steps.ui:report.md"]},
    ],
    "deploy": [
        {"id": "observe", "kind": "skill", "skill": "build/observability-setup", "inputs": {"target": "$repo"},
         "evidence": ["$steps.observe:install-report.md"]},
        {"id": "ci", "kind": "skill", "skill": "build/ci-cd-vercel-github", "inputs": {"target": "$repo"},
         "evidence": ["$steps.ci:ci-report.md"]},
        {"id": "pr", "kind": "pr", "title": "$in.request", "branch": "deliver/$run.id", "body": "$evidence",
         "gate": {"kind": "external", "what": "CI green on the pull request"}, "evidence": ["$steps.pr:pr.json"]},
    ],
    "operate": [
        {"id": "handoff", "kind": "skill", "skill": "build/handoff-and-thread-close", "inputs": {"target": "$repo", "state": "$run.state"},
         "gate": {"kind": "output", "step": "handoff", "file": "HANDOFF.md", "check": "exists"},
         "evidence": ["$steps.handoff:HANDOFF.md"]},
    ],
}
# the ADLC stage each library stage id runs as (bootstrap is a build-stage pass before the profile is read)
ADLC_OF = {"bootstrap": "build"}
INPUTS = {
    "brownfield": [
        {"name": "repo", "type": "repo", "required": True, "from": "catalog repository (owner/name) or a local checkout"},
        {"name": "ref", "type": "string", "required": False, "from": "branch or commit to start from (default: the checkout as it is)"},
        {"name": "request", "type": "text", "required": True, "from": "the request in the requester's words"},
        {"name": "brief", "type": "json", "required": False, "from": "product brief for product-spec-prd (layout: skills/build/product-spec-prd/assets/brief-template.json); may carry `files` or `tasks`"},
    ],
    "greenfield": [
        {"name": "repo", "type": "repo", "required": True, "from": "directory to create the application in (created if absent)"},
        {"name": "name", "type": "string", "required": True, "from": "project name"},
        {"name": "request", "type": "text", "required": True, "from": "what the application must do, in the requester's words"},
        {"name": "brief", "type": "json", "required": False, "from": "product brief for product-spec-prd (layout: skills/build/product-spec-prd/assets/brief-template.json); may carry `files` or `tasks`"},
    ],
}


# ------------------------------------------------------------------ catalog
def load_kinds(path: Path = KINDS_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_kind(kinds: dict, kind: str) -> dict:
    """The kind record (aliases followed). Raises ValueError with the known ids."""
    by_id = {k["id"]: k for k in kinds["kinds"]}
    k = by_id.get(kind)
    if k is None:
        raise ValueError(f"unknown request kind {kind!r} (one of {', '.join(sorted(by_id))})")
    if k.get("alias_of"):
        return by_id[k["alias_of"]]
    return k


def load_catalog(root: Path = ROOT) -> dict:
    """roles (sorted by file name) and the fits of every skill in skills/ (absent = fits anything)."""
    roles = [(p.stem, json.loads(p.read_text(encoding="utf-8"))) for p in sorted((root / "roles").glob("*.json"))]
    fits: dict[str, dict | None] = {}
    for md in sorted((root / "skills").glob("*/*/SKILL.md")):
        s = skillmeta.load_skill(md.parent)
        f = s["metadata"].get("fits")
        fits[f"{md.parent.parent.name}/{md.parent.name}"] = f if isinstance(f, dict) else None
    return {"roles": roles, "fits": fits}


def stacks_from_profile(profile: dict) -> list[str]:
    """Stack signal ids (studio/lib/github/detect.ts) a stack profile (scripts/stack_profile.py) implies. Sorted."""
    s: set[str] = set()
    fw, fl = str(profile.get("framework", "")), str(profile.get("flavour", ""))
    if fw == "nextjs":
        s.update(["nextjs", "react"])
    elif fw in ("remix", "vite-react"):
        s.add("react")
    if fl == "ts":
        s.add("typescript")
    if fl == "python" or fw in ("fastapi", "django", "flask"):
        s.add("python")
    mig = profile.get("migrations_dir")
    if isinstance(mig, str) and mig.startswith("supabase/"):
        s.add("supabase")
    if profile.get("deploy_target") == "vercel":
        s.add("vercel")
    ev = profile.get("evidence") if isinstance(profile.get("evidence"), dict) else {}
    if str(ev.get("deploy_target", "")).startswith(".github/workflows/"):
        s.add("github-actions")
    if profile.get("test_runner") not in (None, "", "none") or profile.get("e2e") not in (None, "", "none"):
        s.add("tests")
    return sorted(s)


def fits_match(fits: dict | None, stacks: list[str], kind: str) -> tuple[bool, str]:
    """(ok, why-not). Absent fits = fits anything; `any` in stacks matches every stack."""
    if not fits:
        return True, ""
    fs = [str(x) for x in (fits.get("stacks") or [])]
    if fs and "any" not in fs and not set(fs) & set(stacks):
        return False, f"stack: fits {', '.join(fs)}; the repository has {', '.join(stacks) or 'no known signal'}"
    fk = [str(x) for x in (fits.get("request_kinds") or [])]
    if fk and kind not in fk:
        return False, f"kind: fits {', '.join(fk)}; the request is a {kind}"
    return True, ""


# ------------------------------------------------------------------ composition
def _refs_in(step: dict) -> dict[str, str]:
    """input name -> step id it references ($steps.<id>:…)."""
    out = {}
    for k, v in (step.get("inputs") or {}).items():
        if isinstance(v, str) and v.startswith("$steps."):
            out[k] = v[len("$steps."):].split(":", 1)[0]
    return out


def _lib(step_id: str) -> dict | None:
    return next((st for steps in LIBRARY.values() for st in steps if st["id"] == step_id), None)


def _step_of(ref: str) -> str:
    return ref[len("$steps."):].split(":", 1)[0]


def compose(stacks: list[str], kind: str, catalog: dict, kinds: dict, mode: str | None = None,
            stages: list[str] | None = None, name: str | None = None) -> dict:
    """The composed pipeline and its decision table: {"pipeline": {...} | None, "decisions": [...], "notes": [...]}."""
    krec = resolve_kind(kinds, kind)
    kid = krec["id"]
    mode = mode or krec.get("mode", "brownfield")
    if mode not in ("brownfield", "greenfield"):
        raise ValueError(f"mode must be brownfield or greenfield, not {mode!r}")
    wanted = list(stages) if stages else list(krec["stages"])
    unknown = [s for s in wanted if s not in LIBRARY or s == "bootstrap"]
    if unknown:
        raise ValueError(f"unknown stage(s) {unknown} (one of {', '.join(k for k in LIBRARY if k != 'bootstrap')})")
    if mode == "greenfield":
        wanted = ["bootstrap"] + list(wanted)
    stacks = sorted(set(stacks))
    decisions: list[dict] = []
    notes: list[str] = []
    present: set[str] = set()              # step ids already in the pipeline (earlier stages)
    composed_stages: list[dict] = []

    for sid in wanted:
        adlc = ADLC_OF.get(sid, sid)
        role = next((n for n, r in catalog["roles"] if adlc in (r.get("stages") or [])), None)
        if role is None:
            raise ValueError(f"no role in roles/ owns the {adlc} stage")
        role_skills = set(next(r for n, r in catalog["roles"] if n == role).get("skills") or [])
        chosen: list[dict] = []            # steps of this stage: carried compose steps first, then library order
        here: set[str] = set()

        def decide(step: str, decision: str, why: str, skill: str | None = None, _sid=sid, _role=role) -> None:
            decisions.append({"stage": _sid, "role": _role, "step": step, **({"skill": skill} if skill else {}), "decision": decision, "why": why})

        def available(step_id: str) -> bool:
            return step_id in present or step_id in here

        def can_carry(step_id: str) -> bool:
            """A compose step (from any library stage) whose own needs are met, recursively."""
            st = _lib(step_id)
            if st is None or st["kind"] != "compose":
                return False
            return all(available(r) or can_carry(r) for r in st.get("requires") or [])

        def write_step(st: dict) -> dict:
            out: dict = {"id": st["id"], "kind": st["kind"]}
            if st["kind"] == "skill":
                out["skill"] = st["skill"]
            elif st["kind"] == "compose":
                out["derive"] = st["derive"]
            elif st["kind"] == "agent":
                out["agent"] = st["agent"]
            if "inputs" in st:
                inputs = {}
                for k, v in st["inputs"].items():
                    if st["kind"] == "agent" and k == "plan":
                        inputs[k] = next(p for p in st["plan_fallback"] if available(_step_of(p)))
                        continue
                    if isinstance(v, str) and v.startswith("$steps.") and not available(_step_of(v)):
                        continue   # an optional input whose step is absent (required ones were checked before)
                    inputs[k] = v
                out["inputs"] = inputs
            if st["kind"] == "compose":
                out["outputs"] = list(st["outputs"])
            elif st["kind"] == "agent" and st.get("produces"):
                out["produces"] = list(st["produces"])
            elif st["kind"] == "agent":
                out["constraints"] = [c for c in st["constraints"] if "nextjs" in stacks or not c.startswith("skills/build/nextjs")]
            elif st["kind"] == "skill" and st.get("step_gate"):
                out["gate"] = True
            elif st["kind"] == "approval":
                out["role"] = role
                out["note"] = st["note"]
            elif st["kind"] == "pr":
                out.update(title=st["title"], branch=st["branch"], body=st["body"])
            return out

        def add(st: dict, why: str) -> None:
            for r in st.get("requires") or []:
                if not available(r):
                    carry(r)
            for k, v in (st.get("inputs") or {}).items():
                if isinstance(v, str) and v.startswith("$steps.") and k in (st.get("optional") or []) and not available(_step_of(v)):
                    decide(st["id"], "note", f"optional input `{k}` dropped: step {_step_of(v)} is not in this pipeline", st.get("skill"))
            chosen.append(write_step(st)); here.add(st["id"])
            decide(st["id"], "chosen", why, st.get("skill"))

        def carry(step_id: str) -> None:
            st = _lib(step_id)
            home = _home(step_id)
            add(st, f"compose {st['derive']} ({'its home stage' if home == sid else f'carried from the absent {home} stage'}): a later step needs {st['outputs'][0]}")

        for st in LIBRARY[sid]:
            k = st["kind"]
            if k == "compose":
                continue   # added where first needed
            if k == "skill":
                if st["skill"] not in role_skills:
                    decide(st["id"], "rejected", f"role {role} does not list {st['skill']}", st["skill"]); continue
                ok, why = fits_match(catalog["fits"].get(st["skill"]), stacks, kid)
                if not ok:
                    decide(st["id"], "rejected", why, st["skill"]); continue
            missing = [r for r in (st.get("requires") or []) if not available(r) and not can_carry(r)]
            plan_ref = None
            if k == "agent":
                plan_ref = next((p for p in st["plan_fallback"] if available(_step_of(p)) or can_carry(_step_of(p))), None)
                if plan_ref is None:
                    missing.append("plan")
            if missing:
                roots = sorted({_root_missing(m, available) for m in missing})
                decide(st["id"], "rejected", f"needs step(s) {', '.join(missing)}: {', '.join(f'{r} ({_home(r)} stage, absent or dropped)' for r in roots)}",
                       st.get("skill")); continue
            if plan_ref and not available(_step_of(plan_ref)):
                carry(_step_of(plan_ref))
            add(st, {"skill": "fits the stack and the request kind; every input resolves",
                     "agent": (f"the files step (plan: {plan_ref}): the files the change touches, derived from tasks.csv when every task names them"
                               if st.get("produces") else f"the build step (plan: {plan_ref})"), "approval": "follows the plan",
                     "pr": "the pull request carries the evidence"}[k])
        elsewhere, unwired = [], []
        for sk in sorted(role_skills - {st.get("skill") for st in LIBRARY[sid] if st.get("skill")}):
            home = next((s for s, steps in LIBRARY.items() if any(st.get("skill") == sk for st in steps)), None)
            (elsewhere if home else unwired).append(f"{sk} ({home})" if home else sk)
        if elsewhere:
            decide("-", "rejected", "wired in another stage by the step library: " + ", ".join(elsewhere))
        if unwired:
            decide("-", "rejected", "no wiring recipe in the step library (inputs not derivable from earlier steps or the profile): " + ", ".join(unwired))

        if not any(s["kind"] == "skill" for s in chosen):
            decide("-", "dropped", f"no skill of role {role} fits {', '.join(stacks) or 'the stack'} for a {kid}: stage dropped")
            notes.append(f"stage {sid} dropped: no skill of role {role} fits the stack ({', '.join(stacks) or 'none'}) for a {kid}")
            continue
        lib_ids = [st["id"] for st in LIBRARY[sid]]
        chosen.sort(key=lambda s: (1, lib_ids.index(s["id"])) if s["id"] in lib_ids else (0, 0))
        present.update(s["id"] for s in chosen)
        gates = [_lib(s["id"])["gate"] for s in chosen if "gate" in _lib(s["id"])]
        if not gates:
            gates = [_lib(s["id"])["fallback_gate"] for s in chosen if "fallback_gate" in _lib(s["id"])]
        gate = gates[0] if len(gates) == 1 else {"kind": "all", "of": gates}
        evidence = [e for s in chosen for e in (_lib(s["id"]).get("evidence") or [])]
        composed_stages.append({"id": sid, "adlc_stage": adlc, "role": role, "steps": chosen, "gate": gate, "evidence": evidence})

    if not composed_stages:
        return {"pipeline": None, "decisions": decisions, "notes": notes + ["nothing composed: no stage kept a fitting skill"]}
    slug = name or f"composed-{kid}-{'-'.join(stacks) or 'any'}"
    pipeline = {
        "name": slug, "version": VERSION,
        "title": f"Composed {kid} pipeline for {', '.join(stacks) or 'an unprofiled repository'}",
        "description": f"Composed by scripts/compose_pipeline.py: {kid} request on a {mode} {', '.join(stacks) or 'unknown'} stack — "
                       f"stages {', '.join(s['id'] for s in composed_stages)}; the step wiring is the shipped templates'."
                       + (" Notes: " + "; ".join(notes) + "." if notes else ""),
        "mode": mode,
        "fits": {"stacks": stacks or ["any"], "request_kinds": [kid]},
        "inputs": INPUTS[mode],
        "stack_profile": {"from": "repo", "detect": "scripts/stack_profile.py",
                          **({"after": "bootstrap"} if composed_stages[0]["id"] == "bootstrap" else {})},
        "stages": composed_stages,
        "outputs": (["$steps.pr:pr.json"] if "pr" in present else []) + ["$evidence"],
        "composed": {"request_kind": kid, "stacks": stacks, "notes": notes},
    }
    return {"pipeline": pipeline, "decisions": decisions, "notes": notes}


def _root_missing(step_id: str, available) -> str:
    """The step that is really missing: a compose step is only missing because something it requires is."""
    st = _lib(step_id)
    if st and st["kind"] == "compose":
        for r in st.get("requires") or []:
            if not available(r):
                return _root_missing(r, available)
    return step_id


def _home(step_id: str) -> str:
    return next((sid for sid, steps in LIBRARY.items() if any(s["id"] == step_id for s in steps)), "?")


def explain(result: dict) -> str:
    rows = [("stage", "role", "step", "skill", "decision", "why")] + [
        (r["stage"], r["role"], r["step"], r.get("skill", ""), r["decision"], r["why"]) for r in result["decisions"]]
    w = [max(len(str(r[i])) for r in rows) for i in range(5)]
    lines = [" | ".join(str(c).ljust(w[i]) if i < 5 else str(c) for i, c in enumerate(r)) for r in rows]
    lines.insert(1, "-+-".join("-" * x for x in w) + "-+-" + "---")
    p = result["pipeline"]
    head = (f"composed: {p['name']} — stages {', '.join(s['id'] for s in p['stages'])}" if p else "composed: nothing")
    return "\n".join([head] + [f"note: {n}" for n in result["notes"]] + lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compose a delivery pipeline from the catalog when no template fits")
    ap.add_argument("--profile", help="stack-profile.json from scripts/stack_profile.py")
    ap.add_argument("--stacks", help="comma-separated stack ids instead of a profile (greenfield: the intended stack)")
    ap.add_argument("--request-kind", required=True, help="one of shared/request-kinds.json")
    ap.add_argument("--mode", choices=["brownfield", "greenfield"], help="default: the request kind's mode")
    ap.add_argument("--stages", help="comma-separated ADLC stages to run instead of the kind's list")
    ap.add_argument("--name", help="pipeline name (default: the --out file stem, else composed-<kind>-<stacks>)")
    ap.add_argument("--out", help="write the pipeline here (pipelines/composed/<name>.json); default: stdout")
    ap.add_argument("--explain", action="store_true", help="print the decision table to stderr (stdout with --out)")
    ap.add_argument("--bundle", action="store_true", help="write {input, pipeline, decisions, notes} instead of the pipeline alone (parity fixtures for the portal)")
    args = ap.parse_args(argv)
    if bool(args.profile) == bool(args.stacks):
        print("error: give exactly one of --profile or --stacks", file=sys.stderr); return 2
    try:
        kinds = load_kinds()
        if args.profile:
            stacks = stacks_from_profile(json.loads(Path(args.profile).read_text(encoding="utf-8")))
        else:
            stacks = [s.strip() for s in args.stacks.split(",") if s.strip()]
            bad = [s for s in stacks if s not in kinds["stacks"] or s == "any"]
            if bad:
                print(f"error: unknown stack id(s) {bad} (one of {', '.join(k for k in kinds['stacks'] if k != 'any')})", file=sys.stderr); return 2
        name = args.name or (Path(args.out).stem if args.out else None)
        result = compose(stacks, args.request_kind, load_catalog(), kinds, mode=args.mode,
                         stages=[s.strip() for s in args.stages.split(",") if s.strip()] if args.stages else None, name=name)
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr); return 2
    if args.explain:
        print(explain(result), file=sys.stdout if args.out else sys.stderr)
    if result["pipeline"] is None:
        print("error: " + "; ".join(result["notes"]), file=sys.stderr); return 1
    bundle = {"input": {"stacks": sorted(set(stacks)), "request_kind": args.request_kind, "mode": args.mode, "stages": args.stages.split(",") if args.stages else None, "name": name},
              "pipeline": result["pipeline"], "decisions": result["decisions"], "notes": result["notes"]}
    text = json.dumps(bundle if args.bundle else result["pipeline"], indent=2) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out} ({len(result['pipeline']['stages'])} stages)")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
