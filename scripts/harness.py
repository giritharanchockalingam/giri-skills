#!/usr/bin/env python3
"""The harness: a goal document becomes a DAG of delivery runs (docs/HARNESS.md layers 2 and 7).

    harness.py plan    --goal GOAL.md --dir D [--name app] [--stack nextjs-ts] [--repo PATH] [--max-slices 8] [--model M]
    harness.py approve --dir D --by NAME [--slice ID] [--note TEXT]      # the slice plan, or the waiting step of one slice
    harness.py run     --dir D [--dry] [--sandbox docker] [--budget-usd N] [--model M] [--approve-all]
    harness.py status  --dir D
    harness.py report  --dir D                                          # D/HARNESS-REPORT.md

plan     the model reads the goal and proposes vertical slices (id, title, depends_on, a product brief each, the goal
         sections it covers) plus what is out of scope; the harness validates the result (schema, unique ids, known
         dependencies, no cycle, at least one root, every slice briefed) and writes D/slices.json and D/briefs/<id>.json.
         The plan is not run until a person approves it (`approve --by`), or `run --approve-all` (recorded AUTO).
run      slices in dependency order, one `deliver.py` run each (the first greenfield, the rest feature-delivery on
         the previous slice's result). D/state.json is written after every transition, so a crash or restart
         resumes the first unfinished slice — and the run inside it with --resume. A slice that stops for a person
         (plan approval, a builder) stops the harness with the exact command to continue.
         --dry chains slices on local copies (the previous slice's diff is committed, standing in for its merged
         PR). Without --dry each slice opens a real pull request in --repo and the harness waits for it to be merged
         into the default branch before the next slice starts (a person merges: the human gate on what ships).
budget   --budget-usd is the whole goal's budget: each slice run gets what is left.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DELIVER = HERE / "deliver.py"
EXIT_OK, EXIT_FAIL, EXIT_ARGS, EXIT_APPROVAL, EXIT_BUILDER = 0, 1, 2, 3, 4
BRIEF_KEYS = ("feature", "problem", "goals")
PLAN_RULES = (
    "Decompose the goal into vertical slices a delivery pipeline can build one at a time. Rules: (1) contracts and the "
    "domain model first, then each slice adds working behaviour end to end with its own tests; (2) a slice is small "
    "enough for one build session (a few hundred to two thousand lines), testable on its own, and names the goal "
    "sections it satisfies; (3) every non-negotiable of the goal that a slice touches is written into that slice's "
    "brief as a goal or constraint, word for word where possible, so its reviewer judges it; (4) depends_on lists the "
    "slices whose code it builds on; (5) anything the pipeline cannot build (a real third-party sandbox, people, "
    "money) goes to out_of_scope with the reason; (6) use only facts from the goal; no invented numbers.")


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p: Path, data) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)                       # atomic: a crash never leaves half a state file


class HarnessError(Exception):
    pass


# ---------------------------------------------------------------- plan

def validate_plan(plan: dict, max_slices: int) -> list[str]:
    """Problems with a proposed slice plan; empty = valid."""
    problems = []
    slices = plan.get("slices")
    if not isinstance(slices, list) or not slices:
        return ["no slices"]
    if len(slices) > max_slices:
        problems.append(f"{len(slices)} slices (max {max_slices})")
    ids = [str(s.get("id", "")) for s in slices]
    if len(set(ids)) != len(ids) or not all(ids):
        problems.append("slice ids must be present and unique")
    known = set(ids)
    for s in slices:
        sid = s.get("id")
        for dep in s.get("depends_on") or []:
            if dep not in known:
                problems.append(f"{sid}: depends on unknown slice {dep}")
            if dep == sid:
                problems.append(f"{sid}: depends on itself")
        b = s.get("brief") or {}
        missing = [k for k in BRIEF_KEYS if not b.get(k)]
        if missing:
            problems.append(f"{sid}: brief lacks {', '.join(missing)}")
        if not s.get("title"):
            problems.append(f"{sid}: no title")
    if not problems:
        try:
            topo_order(slices)
        except HarnessError as e:
            problems.append(str(e))
    if not any(not (s.get("depends_on") or []) for s in slices):
        problems.append("no root slice (every slice depends on another)")
    return problems


def topo_order(slices: list[dict]) -> list[str]:
    """Dependency order, stable by position in the plan; a cycle is an error."""
    deps = {s["id"]: list(s.get("depends_on") or []) for s in slices}
    order, done = [], set()
    while len(order) < len(slices):
        ready = [s["id"] for s in slices if s["id"] not in done and all(d in done for d in deps[s["id"]])]
        if not ready:
            raise HarnessError("the slice dependencies form a cycle: " + ", ".join(sorted(set(deps) - done)))
        order.append(ready[0])
        done.add(ready[0])
    return order


def claude_json(prompt: str, cwd: Path, add_dirs: list[Path], model: str | None, budget: float | None, timeout: int = 1800) -> dict:
    exe = shutil.which("claude")
    if not exe:
        raise HarnessError("`claude` is not on PATH")
    cmd = [exe, *(["--model", model] if model else []), *(["--max-budget-usd", f"{budget:.4f}"] if budget else []),
           "--permission-mode", "acceptEdits", *[x for d in add_dirs for x in ("--add-dir", str(d))],
           "--allowedTools", "Read", "Write", "Glob", "Grep", "LS", "--disallowedTools", "Bash",
           "-p", prompt, "--output-format", "json"]
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise HarnessError(f"planner reply was not JSON (exit {r.returncode}): {(r.stderr or r.stdout)[-300:]}") from None


def cmd_plan(a) -> int:
    d = a.dir.resolve()
    d.mkdir(parents=True, exist_ok=True)
    goal = a.goal.resolve()
    if not goal.is_file():
        raise HarnessError(f"goal document not found: {goal}")
    target = d / "slices.proposed.json"
    target.unlink(missing_ok=True)
    feedback, cost = "", 0.0
    for attempt in (1, 2):
        prompt = (f"Read the goal document {goal}. {PLAN_RULES} At most {a.max_slices} slices. Write {target} as JSON: "
                  '{"slices": [{"id": "S1", "title": "...", "depends_on": [], "goal_sections": ["..."], '
                  '"brief": {"feature": "...", "problem": "...", "users": ["..."], "goals": ["..."], "non_goals": ["..."], '
                  '"constraints": ["..."], "metrics": [{"name": "...", "baseline": "...", "target": "..."}], '
                  '"phases": [{"name": "...", "scope": ["..."]}]}}], "out_of_scope": [{"what": "...", "why": "..."}]}.'
                  + feedback)
        meta = claude_json(prompt, d, [goal.parent], a.model, None if a.budget_usd is None else a.budget_usd - cost)
        cost += float(meta.get("total_cost_usd") or 0)          # every attempt is paid for, the refused one too
        try:
            plan = read_json(target)
        except (OSError, json.JSONDecodeError) as e:
            raise HarnessError(f"the planner wrote no valid {target.name} ({e})") from None
        problems = validate_plan(plan, a.max_slices)
        if not problems:
            break
        feedback = " Your previous plan was refused by the harness: " + "; ".join(problems) + ". Fix exactly these."
        target.unlink(missing_ok=True)
    if problems:
        raise HarnessError("slice plan refused after a repair turn: " + "; ".join(problems))
    (d / "briefs").mkdir(exist_ok=True)
    for s in plan["slices"]:
        brief = {"_note": f"Slice {s['id']} of the goal {goal.name}; the full goal document is docs/{goal.name} in the repository.", **s["brief"]}
        write_json(d / "briefs" / f"{s['id']}.json", brief)
    plan.update(goal=str(goal), planned_at=now(), planner_model=a.model or "claude-code default",
                planner_cost_usd=round(cost, 4), order=topo_order(plan["slices"]))
    write_json(d / "slices.json", plan)
    target.unlink(missing_ok=True)
    state = {"goal": str(goal), "name": a.name, "stack": a.stack, "repo": str(a.repo.resolve()) if a.repo else None,
             "plan_approval": None, "slices": {s["id"]: {"status": "pending"} for s in plan["slices"]},
             "cost_usd": round(cost, 4), "log": [{"at": now(), "event": "planned", "slices": len(plan["slices"])}]}
    write_json(d / "state.json", state)
    print(f"plan: {len(plan['slices'])} slices in order {' -> '.join(plan['order'])}; "
          f"{len(plan.get('out_of_scope') or [])} item(s) out of scope — review {d / 'slices.json'}, then:\n"
          f"  python3 {Path(__file__).resolve()} approve --dir {d} --by <your name>")
    return EXIT_OK


# ---------------------------------------------------------------- approve / status

def load(d: Path) -> tuple[dict, dict]:
    if not (d / "state.json").is_file():
        raise HarnessError(f"no harness here: {d / 'state.json'} (run `plan` first)")
    return read_json(d / "slices.json"), read_json(d / "state.json")


def save_state(d: Path, state: dict, event: str, **kw) -> None:
    state.setdefault("log", []).append({"at": now(), "event": event, **kw})
    write_json(d / "state.json", state)


def cmd_approve(a) -> int:
    d = a.dir.resolve()
    plan, state = load(d)
    if not a.slice:
        state["plan_approval"] = {"by": a.by, "note": a.note or "", "at": now(), "source": "person"}
        save_state(d, state, "plan approved", by=a.by)
        print(f"slice plan approved by {a.by}")
        return EXIT_OK
    st = state["slices"].get(a.slice)
    if st is None:
        raise HarnessError(f"unknown slice {a.slice}")
    out = Path(st.get("out") or "")
    need = out / "needs_approval.json"
    if not need.is_file():
        raise HarnessError(f"slice {a.slice} is not waiting for an approval (no {need})")
    step = read_json(need)["step"]
    r = subprocess.run([sys.executable, str(DELIVER), "approve", str(out), "--step", step, "--by", a.by,
                        *(["--note", a.note] if a.note else [])], capture_output=True, text=True)
    if r.returncode != 0:
        raise HarnessError(f"deliver approve failed: {(r.stderr or r.stdout).strip()[-300:]}")
    st.setdefault("approvals", []).append({"step": step, "by": a.by, "note": a.note or "", "at": now()})
    save_state(d, state, "slice step approved", slice=a.slice, step=step, by=a.by)
    print(f"{a.slice}: step '{step}' approved by {a.by} — continue with `run`")
    return EXIT_OK


def cmd_status(a) -> int:
    plan, state = load(a.dir.resolve())
    pa = state.get("plan_approval") or {}
    print(f"goal {Path(state['goal']).name}; plan approved by: {pa.get('by') or 'NOT APPROVED'}; spend ${state.get('cost_usd', 0):.2f}")
    for sid in plan["order"]:
        st = state["slices"][sid]
        s = next(x for x in plan["slices"] if x["id"] == sid)
        print(f"  {sid:4} {st['status']:18} {s['title'][:60]}" + (f"  — {st.get('detail', '')[:80]}" if st.get("detail") else ""))
    return EXIT_OK


# ---------------------------------------------------------------- run

def run_json(out: Path) -> dict:
    return read_json(out / "run.json") if (out / "run.json").is_file() else {}


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def merged(repo: Path, branch: str) -> bool:
    git(repo, "fetch", "-q", "origin")
    head = git(repo, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD").stdout.strip() or "origin/main"
    br = git(repo, "rev-parse", "-q", "--verify", f"origin/{branch}").stdout.strip()
    if br and git(repo, "merge-base", "--is-ancestor", br, head).returncode == 0:
        return True
    # squash merges leave no ancestry: a merged PR is the authority when gh is available
    if shutil.which("gh"):
        r = subprocess.run(["gh", "pr", "view", branch, "--json", "state", "-q", ".state"], cwd=str(repo), capture_output=True, text=True)
        return r.stdout.strip() == "MERGED"
    return False


def cmd_run(a) -> int:
    d = a.dir.resolve()
    plan, state = load(d)
    if not state.get("plan_approval"):
        if not a.approve_all:
            print(f"the slice plan is not approved: review {d / 'slices.json'}, then\n"
                  f"  python3 {Path(__file__).resolve()} approve --dir {d} --by <your name>")
            return EXIT_APPROVAL
        state["plan_approval"] = {"by": "--approve-all", "note": "AUTO-APPROVED: no person reviewed the slice plan", "at": now(), "source": "cli"}
        save_state(d, state, "plan auto-approved")
    goal = Path(state["goal"])
    for sid in plan["order"]:
        s = next(x for x in plan["slices"] if x["id"] == sid)
        st = state["slices"][sid]
        if st["status"] == "passed":
            continue
        blocked = [dep for dep in s.get("depends_on") or [] if state["slices"][dep]["status"] != "passed"]
        if blocked:
            raise HarnessError(f"{sid} depends on unfinished {blocked}")   # topo order makes this unreachable unless state was edited
        if st["status"] == "awaiting_merge":
            if merged(Path(state["repo"]), st["branch"]):
                st["status"] = "passed"
                save_state(d, state, "slice merged", slice=sid, branch=st["branch"])
                continue
            print(f"{sid}: waiting for its pull request ({st['branch']}) to be merged; run again after merging")
            return EXIT_APPROVAL
        spent = float(state.get("cost_usd") or 0)
        if a.budget_usd is not None and spent >= a.budget_usd:
            st.update(status="failed", detail=f"goal budget exhausted: ${spent:.2f} of ${a.budget_usd:.2f}")
            save_state(d, state, "budget exhausted", slice=sid)
            print(f"stopped: {st['detail']}")
            return EXIT_FAIL
        out = Path(st.get("out") or d / "runs" / sid)
        resume = (out / "run.json").is_file() and st["status"] in ("running", "awaiting_approval", "awaiting_builder", "failed")
        first = sid == plan["order"][0] and not state.get("repo")
        if first:
            repo = d / "app"
            if not resume and not repo.exists():
                (repo / "docs").mkdir(parents=True)
                shutil.copy(goal, repo / "docs" / goal.name)          # the goal travels with the code
            pipeline = ["greenfield-app", "--repo", str(repo), "--input", f"name={state.get('name') or 'app'}",
                        "--input", f"stack={state.get('stack') or 'nextjs-ts'}"]
        else:
            prev = next((x for x in reversed(plan["order"][:plan["order"].index(sid)]) if state["slices"][x]["status"] == "passed"), None)
            if a.dry:
                base = Path(state["slices"][prev]["out"]) / "repo" if prev else Path(state["repo"])
                if prev and not resume:
                    git(base, "add", "-A")
                    git(base, "-c", "user.name=harness", "-c", "user.email=harness@local", "-c", "commit.gpgsign=false",
                        "commit", "-qm", f"merge {prev} (dry run: the slice's diff, standing in for its merged PR)")
            else:
                base = Path(state["repo"])
                if not resume:
                    git(base, "checkout", "-q", git(base, "rev-parse", "--abbrev-ref", "origin/HEAD").stdout.strip().split("/")[-1] or "main")
                    git(base, "pull", "-q", "--ff-only")
            pipeline = ["feature-delivery", "--repo", str(base)]
        left = None if a.budget_usd is None else round(a.budget_usd - spent, 4)
        argv = [sys.executable, "-I", str(DELIVER), *pipeline, "--request", s["brief"]["feature"], "--brief", str(d / "briefs" / f"{sid}.json"),
                "--goal", str(goal), "--builder", "claude-code", "--provider", "none", "--out", str(out),
                "--sandbox", a.sandbox, "--acceptance", "on", "--rounds", str(a.rounds), *(["--model", a.model] if a.model else []),
                *(["--budget-usd", f"{left:.4f}"] if left is not None else []), *(["--dry"] if a.dry else []),
                *(["--approve-all"] if a.approve_all else []), *(["--resume"] if resume else [])]
        st.update(status="running", out=str(out), started_at=st.get("started_at") or now(), argv=argv)
        save_state(d, state, "slice started" if not resume else "slice resumed", slice=sid)
        print(f"{sid}: {s['title']} ({'resume' if resume else 'start'})", flush=True)
        log = d / "runs" / f"{sid}.console.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as fh:
            rc = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT).returncode
        rj = run_json(out)
        state["cost_usd"] = round(spent + float((rj.get("llm") or {}).get("cost_usd") or 0) - float(st.get("cost_usd") or 0), 4)
        st["cost_usd"] = float((rj.get("llm") or {}).get("cost_usd") or 0)
        st["detail"] = (open(log, encoding="utf-8").read().strip().splitlines() or [""])[-1][:300]
        if rc == EXIT_OK:
            pr = None if a.dry else next((x for g in rj.get("stages", []) for x in g.get("steps", [])
                                          if x.get("kind") == "pr" and x.get("branch")), None)
            if pr:
                st.update(status="awaiting_merge", branch=pr["branch"])
                save_state(d, state, "slice PR opened", slice=sid, branch=st["branch"])
                print(f"{sid}: pull request opened ({st['branch']}); merge it, then run again")
                return EXIT_APPROVAL
            st["status"] = "passed"
            save_state(d, state, "slice passed", slice=sid)
            continue
        status = {EXIT_APPROVAL: "awaiting_approval", EXIT_BUILDER: "awaiting_builder"}.get(rc, "failed")
        st["status"] = status
        save_state(d, state, f"slice {status}", slice=sid, exit=rc)
        if status == "awaiting_approval":
            print(f"{sid}: waiting for a person to approve — review {out / 'needs_approval.json'}, then\n"
                  f"  python3 {Path(__file__).resolve()} approve --dir {d} --slice {sid} --by <your name>\n  and run again")
            return EXIT_APPROVAL
        print(f"{sid}: {status} — {st['detail']}")
        return EXIT_BUILDER if status == "awaiting_builder" else EXIT_FAIL
    save_state(d, state, "goal complete")
    write_report(d)
    print(f"all {len(plan['order'])} slices passed — {d / 'HARNESS-REPORT.md'}")
    return EXIT_OK


# ---------------------------------------------------------------- report

def write_report(d: Path) -> Path:
    plan, state = load(d)
    pa = state.get("plan_approval") or {}
    lines = [f"# Harness report — {Path(state['goal']).name}", "",
             f"Slice plan approved by: **{pa.get('by') or 'NOT APPROVED'}**" + (" (AUTO-APPROVED: no person reviewed it)" if pa.get("by") == "--approve-all" else ""),
             f"Total model spend: ${float(state.get('cost_usd') or 0):.2f}", "",
             "| Slice | Title | Status | Stages passed | Tests | Acceptance | Repairs | Sandbox | Cost |", "|---|---|---|---|---|---|---|---|---|"]
    for sid in plan["order"]:
        s = next(x for x in plan["slices"] if x["id"] == sid)
        st = state["slices"][sid]
        rj = run_json(Path(st["out"])) if st.get("out") else {}
        stages = rj.get("stages") or []
        code = next((x for g in stages for x in g.get("steps", []) if x.get("id") == "code"), {})
        acc = code.get("acceptance") or {}
        cnt = acc.get("counts") or {}
        acc_s = (f"{str(acc.get('verdict')).upper()} (MET {cnt.get('MET', 0)}, PARTLY {cnt.get('PARTLY', 0)}, NOT MET {cnt.get('NOT_MET', 0)}, "
                 f"UNVERIFIED {cnt.get('UNVERIFIED', 0)})" if cnt else str(acc.get("verdict") or "—"))
        lines.append(f"| {sid} | {s['title'][:50]} | {st['status']} | {sum((g.get('gate') or {}).get('verdict') == 'pass' for g in stages)}/{len(stages)} | "
                     f"{(code.get('tests') or {}).get('summary') or '—'} | {acc_s} | {len(code.get('repairs') or [])} | "
                     f"{(rj.get('sandbox') or {}).get('mode', 'none')} | ${float(st.get('cost_usd') or 0):.2f} |")
    oos = plan.get("out_of_scope") or []
    if oos:
        lines += ["", "## Out of scope (stated by the plan)", ""] + [f"- {o.get('what')}: {o.get('why')}" for o in oos]
    lines += ["", "## Log", ""] + [f"- {e['at']} {e['event']}" + "".join(f" {k}={v}" for k, v in e.items() if k not in ("at", "event")) for e in state.get("log", [])[-40:]]
    p = d / "HARNESS-REPORT.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--goal", type=Path, required=True)
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--name", default="app")
    p.add_argument("--stack", default="nextjs-ts")
    p.add_argument("--repo", type=Path, help="existing repository the slices build on (default: greenfield in DIR/app)")
    p.add_argument("--max-slices", type=int, default=8)
    p.add_argument("--model")
    p.add_argument("--budget-usd", type=float)
    p = sub.add_parser("approve")
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--slice")
    p.add_argument("--note")
    p = sub.add_parser("run")
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--dry", action="store_true")
    p.add_argument("--sandbox", choices=["docker", "none"], default="docker")
    p.add_argument("--budget-usd", type=float)
    p.add_argument("--model")
    p.add_argument("--rounds", type=int, default=4, help="repair turns per slice (tests, benchmark, visual and acceptance all draw on them; "
                   "found on the R7 run: 2 were spent before the acceptance fix could be re-tested)")
    p.add_argument("--approve-all", action="store_true", help="AUTO-approve the slice plan and every plan approval (recorded as such)")
    for name in ("status", "report"):
        p = sub.add_parser(name)
        p.add_argument("--dir", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "report":
            print(write_report(a.dir.resolve()))
            return EXIT_OK
        return {"plan": cmd_plan, "approve": cmd_approve, "run": cmd_run, "status": cmd_status}[a.cmd](a)
    except HarnessError as e:
        print(f"harness: {e}", file=sys.stderr)
        return EXIT_ARGS


if __name__ == "__main__":
    sys.exit(main())
