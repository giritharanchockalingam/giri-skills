#!/usr/bin/env python3
"""Run a delivery pipeline (pipelines/<name>.json) against a real repository — docs/DELIVERY-PIPELINES.md.

    python3 scripts/deliver.py feature-delivery --repo ./app --request "Export orders as CSV" \
        [--brief brief.json] [--ref main] [--input name=value ...] --out ./runs/r1 \
        --builder none|manual|claude-code [--provider dry|none|anthropic|openai] \
        [--approve-all | --approvals approvals.json] [--patch diff.patch] [--dry] [--resume] [--run-id ID]

Order of work: the stack profile (scripts/stack_profile.py, once, before stage 1 — or after the stage the
pipeline's `stack_profile.after` names), then the stages in order. Step kinds:
  skill     scripts/run_skill.py in a subprocess, inputs resolved from references; an optional input that
            resolves to nothing is omitted; `gate: true` means exit 1 fails the stage at once
  compose   a deterministic derivation (brief-from-request, spec-from-prd, feature-from-plan)
  approval  blocks: needs_approval.json is written and the run exits 3, unless --approve-all or the
            --approvals file records the step ({"approvals": [{"step": "<id>", "by": "...", "note": "..."}]})
  agent     --builder none        -> needs_builder.json, exit 4: a person or IDE agent writes the code and
                                     drops the diff at <out>/build/diff.patch, then re-runs with --resume
            --builder manual      -> <out>/build/diff.patch must exist (nothing is applied; it is recorded)
            --builder claude-code -> `claude -p` on the checkout with a prompt built from the plan, the test
                                     plan and the constraint files; `git diff` is captured as diff.patch
  pr        --dry writes pr.json {"dry": true}; otherwise `gh pr create` on branch deliver/<run-id> with
            EVIDENCE.md as the body
Gates per the doc (output / exit / approval / all / any / external). A failed gate stops the run with exit 1
and the evidence so far.

Evidence bundle under <out>/evidence/: stack-profile.json, one folder per stage (<nn>-<stage>/<step>/… outputs
and gate.json) and EVIDENCE.md (the table that goes into the PR body). <out>/run.json records stages, steps,
exit codes, durations and the sha256 of every evidence file. --dry works on a copy of the repo under
<out>/repo (git-initialised with a fixed identity, so the run is reproducible); otherwise the checkout is used
in place. --resume continues an existing <out> from the first incomplete stage (completed steps are kept).

Exit codes: 0 every stage passed · 1 a gate or step failed · 2 bad arguments / missing input (needs_input.json)
· 3 waiting for an approval (needs_approval.json) · 4 waiting for the builder (needs_builder.json).
Stdlib only; deterministic apart from the timestamps in run.json.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import check_output  # noqa: E402
import validate_pipelines as vp  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_ARGS, EXIT_APPROVAL, EXIT_BUILDER = 0, 1, 2, 3, 4
TBD_RE = re.compile(r"\[TO BE BASELINED[^\]]*\]")
GIT_ENV = {"GIT_AUTHOR_NAME": "deliver", "GIT_AUTHOR_EMAIL": "deliver@giri-skills.local",
           "GIT_COMMITTER_NAME": "deliver", "GIT_COMMITTER_EMAIL": "deliver@giri-skills.local",
           "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
COPY_IGNORE = shutil.ignore_patterns("node_modules", ".next", "dist", "coverage", ".turbo", "__pycache__", ".venv")
CONTEXT_LIMIT = 12 * 1024


class StepError(Exception):
    pass


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def git(repo: Path, *args: str, ok=(0,)) -> tuple[int, str]:
    r = subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=str(repo), capture_output=True, text=True,
                       env={**os.environ, **GIT_ENV})
    if r.returncode not in ok:
        raise StepError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:300]}")
    return r.returncode, r.stdout


def is_git_root(p: Path) -> bool:
    return (p / ".git").exists()


# ------------------------------------------------------------------ compose derivations

def first_line(text: str, limit: int = 80) -> str:
    line = next((ln.strip() for ln in str(text).splitlines() if ln.strip()), "").rstrip(".")
    return line[:limit].strip()


def derive_brief(inputs: dict, sdir: Path) -> None:
    brief_path = inputs.get("brief")
    if brief_path:
        try:
            data = read_json(Path(brief_path))
        except (OSError, ValueError) as e:
            raise StepError(f"brief is not valid JSON: {e}")
        if not isinstance(data, dict) or not str(data.get("feature", "")).strip():
            raise StepError("brief.json must be an object with at least `feature` and `problem`")
        data.setdefault("problem", first_line(inputs.get("request", "")))
    else:
        request = str(inputs.get("request", "")).strip()
        if not request:
            raise StepError("no brief and an empty request: nothing to derive a brief from")
        data = {"feature": first_line(request), "problem": request,
                "_composed": "by deliver.py from the request text only; users, goals, non-goals, metrics and phases "
                             "are to be baselined by the Product owner"}
    write_json(sdir / "brief.json", data)


def _task_bullet(text: str, fields: dict) -> str:
    inline = "; ".join(f"{k}: {v}" for k, v in fields.items() if str(v).strip())
    return f"- {text}" + (f" ({inline})" if inline else "")


def derive_spec(inputs: dict, sdir: Path) -> None:
    brief = read_json(Path(inputs["brief"])) if inputs.get("brief") else {}
    request = str(inputs.get("request", ""))
    feature = str(brief.get("feature") or first_line(request) or "Feature").strip()
    files_all = ",".join(str(f).strip() for f in (brief.get("files") or []) if str(f).strip())
    bullets: list[str] = []
    source = ""
    tasks = brief.get("tasks")
    if isinstance(tasks, list) and tasks:
        source = "brief.tasks"
        for t in tasks:
            if isinstance(t, dict) and str(t.get("task", "")).strip():
                files = ",".join(t["files"]) if isinstance(t.get("files"), list) else str(t.get("files") or files_all)
                bullets.append(_task_bullet(str(t["task"]).strip(), {"accept": t.get("accept") or t.get("acceptance", ""),
                                                                     "test": t.get("test", ""), "rollback": t.get("rollback", ""),
                                                                     "files": files, "size": t.get("size", "")}))
            elif isinstance(t, str) and t.strip():
                bullets.append(_task_bullet(t.strip(), {"files": files_all}))
    if not bullets:
        phases = brief.get("phases") or []
        scope = (phases[0].get("scope") if phases and isinstance(phases[0], dict) else None) or []
        if scope:
            source = f"brief.phases[0] ({phases[0].get('name', 'v1')}).scope"
            bullets = [_task_bullet(str(s).strip(), {"files": files_all}) for s in scope if str(s).strip()]
    if not bullets and brief.get("goals"):
        source = "brief.goals"
        bullets = [_task_bullet(str(g).strip(), {"files": files_all}) for g in brief["goals"] if str(g).strip()]
    if not bullets:
        source = "request"
        bullets = [_task_bullet(first_line(request) or feature, {"files": files_all})]
    md = ["# Specification", "",
          "Composed by deliver.py from brief.json and prd-final.md — nothing invented; fields the brief does not give "
          "are marked to be baselined by spec-to-plan.", "",
          f"PRD: prd-final.md · tasks from {source}", "", f"## {feature}", ""] + bullets + [""]
    (sdir / "spec.md").write_text("\n".join(md), encoding="utf-8")
    write_json(sdir / "spec.json", {"section": feature, "n_tasks": len(bullets), "tasks_from": source,
                                    "files": files_all, "source": {"brief": "brief.json", "prd": "prd-final.md"}})


def derive_feature(inputs: dict, sdir: Path) -> None:
    tasks_path = Path(inputs["tasks"])
    rows = list(csv.DictReader(io.StringIO(tasks_path.read_text(encoding="utf-8"))))
    brief = read_json(Path(inputs["brief"])) if inputs.get("brief") else {}
    plan_text = Path(inputs["plan"]).read_text(encoding="utf-8", errors="replace") if inputs.get("plan") else ""
    h1 = next((ln.lstrip("# ").strip() for ln in plan_text.splitlines() if ln.startswith("# ")), "")
    title = str(brief.get("feature") or h1 or "Feature").strip()
    criteria, files, seen = [], [], set()
    for r in rows:
        acc = (r.get("acceptance") or "").strip()
        task = (r.get("task") or "").strip()
        crit = task if (not acc or TBD_RE.search(acc)) else acc
        if crit and crit not in criteria:
            criteria.append(crit)
        cell = (r.get("files") or "").strip()
        if not cell or TBD_RE.search(cell):
            continue  # the plan did not name files: never invent them
        for f in re.split(r"[,;]+", cell):
            f = f.strip().strip("`")
            if f and f not in seen:
                seen.add(f); files.append(f)
    files_source = "tasks.csv" if files else ""
    if not files and brief.get("files"):
        files = [str(f).strip() for f in brief["files"] if str(f).strip()]
        files_source = "brief.json"
    if not criteria:
        raise StepError("tasks.csv has no tasks to derive acceptance criteria from")
    (sdir / "feature.md").write_text(f"# {title}\n\n" + "".join(f"- {c}\n" for c in criteria), encoding="utf-8")
    write_json(sdir / "feature.json", {"title": title, "files": ",".join(files), "criteria": len(criteria),
                                       "files_source": files_source or "none — name the files in the brief (`files`) or in tasks.csv before the build"})


DERIVE = {"brief-from-request": derive_brief, "spec-from-prd": derive_spec, "feature-from-plan": derive_feature}


# ------------------------------------------------------------------ the run

class Run:
    def __init__(self, spec: dict, args, out: Path):
        self.spec, self.args, self.out = spec, args, out
        self.evidence = out / "evidence"
        self.record: dict = {}
        self.step_dirs: dict[str, Path] = {}
        self.inputs: dict = {}
        self.repo: Path | None = None
        self.profile: dict = {}
        self.run_id = ""
        self.mode = "dry" if args.provider == "dry" else "real"

    # ---- references
    def resolve(self, value, where: str = ""):
        if not isinstance(value, str) or not value.startswith("$"):
            return value
        if value == "$repo":
            return str(self.repo)
        if value == "$evidence":
            return str(self.evidence / "EVIDENCE.md")
        m = vp.IN_REF.match(value)
        if m:
            return self.inputs.get(m.group(1), "")
        m = vp.RUN_REF.match(value)
        if m:
            return {"id": self.run_id, "state": self.state_line(), "draft_only": "true" if self.args.provider in ("dry", "none") else ""}[m.group(1)]
        m = vp.PROFILE_REF.match(value)
        if m:
            v = self.profile.get(m.group(1))
            if m.group(2) is not None:
                v = v.get(m.group(2)) if isinstance(v, dict) else None
            return "" if v is None else v
        m = vp.STEP_REF.match(value)
        if m:
            sid, rel, key = m.group(1), m.group(2), m.group(3)
            if sid not in self.step_dirs:
                raise StepError(f"{where}: step '{sid}' has not run")
            path = self.step_dirs[sid] / rel
            if not path.is_file():
                raise StepError(f"{where}: step '{sid}' did not write {rel}")
            if not key:
                return str(path)
            cur = read_json(path)
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    raise StepError(f"{where}: key '{key}' not in {rel}")
            return cur
        raise StepError(f"{where}: bad reference {value!r}")

    def subst(self, text: str) -> str:
        """`deliver/$run.id`-style strings: substitute embedded $run.* and $in.* tokens."""
        text = re.sub(r"\$run\.id\b", self.run_id, str(text))
        return re.sub(r"\$in\.([A-Za-z_][\w-]*)", lambda m: str(self.inputs.get(m.group(1), "")), text)

    def state_line(self) -> str:
        done = [s for s in self.record.get("stages", []) if s.get("status") == "passed"]
        total = len(self.spec["stages"])
        pr = next((s for s in done if s["id"] == "deploy"), None)
        pr_note = " · PR dry (not opened)" if self.args.dry else (" · PR opened" if pr else "")
        return f"green — {self.spec['name']} run {self.run_id}: {len(done)} of {total} stages passed{pr_note}"

    # ---- stack profile
    def read_profile(self) -> None:
        detect = ROOT / str(self.spec["stack_profile"]["detect"])
        dest = self.evidence / "stack-profile.json"
        r = subprocess.run([sys.executable, "-I", str(detect), str(self.repo), "--json", str(dest)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not dest.is_file():
            raise StepError(f"stack profile failed: {(r.stderr or r.stdout).strip()[:300]}")
        self.profile = read_json(dest)
        self.record["stack_profile"] = {k: self.profile.get(k) for k in ("flavour", "framework", "package_manager",
                                                                          "test_runner", "e2e", "deploy_target",
                                                                          "migrations_dir", "monorepo_root")}

    # ---- steps
    def step_skill(self, step: dict, sdir: Path, rec: dict) -> None:
        argv = [sys.executable, "-I", str(HERE / "run_skill.py"), step["skill"], "--out", str(sdir),
                "--provider", self.args.provider]
        given = {}
        for k, v in (step.get("inputs") or {}).items():
            val = self.resolve(v, f"step '{step['id']}' input '{k}'")
            if val is None or str(val) == "":
                continue  # optional input not available: the skill applies its own rule
            given[k] = str(val)
            argv += ["--input", f"{k}={val}"]
        rec["inputs"] = given
        r = subprocess.run(argv, capture_output=True, text=True, cwd=str(ROOT), timeout=1800)
        (sdir / "deliver-step.log").write_text(r.stdout + r.stderr, encoding="utf-8")
        rec["exit"] = r.returncode
        rj = sdir / "run.json"
        if rj.is_file():
            data = read_json(rj)
            checks = data.get("checks") or []
            rec["checks_passed"] = sum(bool(c.get("pass")) for c in checks)
            rec["checks_total"] = len(checks)
            failed = [f"{Path(c.get('path', '')).name}: {c.get('check')} — {c.get('evidence')}" for c in checks if not c.get("pass")]
            if failed:
                rec["failed_checks"] = failed[:6]
        if r.returncode == 2:
            ni = sdir / "needs_input.json"
            missing = [m.get("name") for m in read_json(ni).get("missing", [])] if ni.is_file() else []
            raise StepError(f"skill {step['skill']} needs input {missing}: not produced by any earlier step")
        if r.returncode >= 3:
            tail = (r.stderr or r.stdout).strip().splitlines()
            raise StepError(f"skill {step['skill']} failed (exit {r.returncode}): {tail[-1] if tail else ''}"[:300])
        if r.returncode == 1 and step.get("gate"):
            raise StepError(f"gate step {step['skill']} said no (exit 1): " + "; ".join(rec.get("failed_checks") or ["see report"])[:300])

    def step_compose(self, step: dict, sdir: Path, rec: dict) -> None:
        fn = DERIVE.get(str(step.get("derive")))
        if fn is None:
            raise StepError(f"unknown derivation {step.get('derive')!r}")
        inputs = {k: self.resolve(v, f"step '{step['id']}' input '{k}'") for k, v in (step.get("inputs") or {}).items()}
        rec["inputs"] = {k: str(v) for k, v in inputs.items()}
        fn(inputs, sdir)
        rec["exit"] = 0
        rec["outputs"] = list(step.get("outputs") or [])

    def step_approval(self, step: dict, sdir: Path, rec: dict, approvals: dict) -> bool:
        rec["role"], rec["note"] = step.get("role", ""), step.get("note", "")
        ap = approvals.get(step["id"])
        if self.args.approve_all and ap is None:
            ap = {"by": "--approve-all", "note": "approved on the command line"}
        if ap is None:
            rec["status"] = "awaiting_approval"
            write_json(self.out / "needs_approval.json", {
                "run_id": self.run_id, "pipeline": self.spec["name"], "stage": rec["stage"], "step": step["id"],
                "role": step.get("role", ""), "note": step.get("note", ""),
                "review": [str(p.relative_to(self.out)) for p in sorted(self.step_dirs.get(step["id"], sdir).parent.rglob("*")) if p.is_file() and p.suffix in (".md", ".csv")][:12],
                "how": "re-run with --resume and --approvals approvals.json "
                       f"({{\"approvals\": [{{\"step\": \"{step['id']}\", \"by\": \"<name>\", \"note\": \"...\"}}]}}), or --approve-all"})
            return False
        rec.update(status="approved", approved_by=str(ap.get("by", "")), at=now(), exit=0)
        write_json(sdir / "approval.json", {"step": step["id"], "role": step.get("role", ""), "status": "approved",
                                            "by": str(ap.get("by", "")), "note": str(ap.get("note", "")), "at": rec["at"]})
        return True

    def _plan_files(self, plan_path: str) -> list[str]:
        text = Path(plan_path).read_text(encoding="utf-8", errors="replace") if plan_path and Path(plan_path).is_file() else ""
        files = set()
        for m in re.finditer(r"^\s*-\s*Files:\s*(.+)$", text, re.M):  # spec-to-plan task blocks: "- Files: a,b"
            files |= {f.strip().strip("`") for f in re.split(r"[,\s;]+", m.group(1)) if "/" in f or "." in f}
        return sorted(f for f in files if f and not TBD_RE.search(f))

    def _record_diff(self, patch: Path, sdir: Path, rec: dict, plan_path: str, summary: str) -> None:
        text = patch.read_text(encoding="utf-8", errors="replace")
        changed = sorted({m.group(1) for m in re.finditer(r"^\+\+\+ b/(\S+)", text, re.M)}
                         | {m.group(1) for m in re.finditer(r"^--- a/(\S+)", text, re.M)})
        plan_files = self._plan_files(plan_path)
        outside = [f for f in changed if plan_files and f not in plan_files and not re.search(r"(^|/)(tests?|__tests__|e2e)/", f)]
        shutil.copy(patch, sdir / "diff.patch")
        write_json(sdir / "files-changed.json", {"files": changed, "plan_files": plan_files, "outside_plan": outside,
                                                 "lines_added": sum(1 for ln in text.splitlines() if ln.startswith("+") and not ln.startswith("+++")),
                                                 "lines_removed": sum(1 for ln in text.splitlines() if ln.startswith("-") and not ln.startswith("---"))})
        md = [f"# Builder summary — {self.args.builder}", "", summary.strip() or "(no summary)", "",
              "## Files changed", ""] + [f"- `{f}`" + (" — NOT named in the plan" if f in outside else "") for f in changed] + [""]
        (sdir / "agent-summary.md").write_text("\n".join(md), encoding="utf-8")
        rec.update(exit=0, files_changed=len(changed), outside_plan=outside)

    def _apply_to_copy(self, patch: Path, target: Path) -> str:
        if not shutil.which("git") or not is_git_root(target):
            return "not applied to the dry copy (no git)."
        body = "\n".join(ln for ln in patch.read_text(encoding="utf-8", errors="replace").splitlines()
                         if not ln.startswith("# ")) + "\n"  # a fixture comment line above the first `diff --git`
        clean = target / ".deliver-apply.patch"
        clean.write_text(body, encoding="utf-8")
        try:
            r = subprocess.run(["git", "apply", "--check", clean.name], cwd=str(target), capture_output=True, text=True)
            if r.returncode != 0:
                return f"NOT applied to the dry copy — git apply --check: {(r.stderr or r.stdout).strip()[:200]}"
            subprocess.run(["git", "apply", clean.name], cwd=str(target), capture_output=True, text=True, check=True)
            return "applied to the dry working copy so the lint and review stages assess the change."
        except subprocess.CalledProcessError as e:
            return f"NOT applied to the dry copy — git apply: {(e.stderr or e.stdout or '').strip()[:200]}"
        finally:
            clean.unlink(missing_ok=True)

    def step_agent(self, step: dict, sdir: Path, rec: dict) -> bool:
        builder = self.args.builder
        rec["builder"] = builder
        plan = str(self.resolve(step["inputs"].get("plan"), "agent plan"))
        tests = str(self.resolve(step["inputs"].get("tests", ""), "agent tests") or "")
        target = Path(str(self.resolve(step["inputs"].get("target", "$repo"), "agent target")))
        manual_patch = self.out / "build" / "diff.patch"
        if builder in ("none", "manual"):
            if manual_patch.is_file():
                note = "nothing was applied by deliver.py (the checkout already carries the change)."
                if self.args.dry:  # the checkout is a throwaway copy: land the diff so the lint stages assess the change
                    note = self._apply_to_copy(manual_patch, target)
                self._record_diff(manual_patch, sdir, rec, plan, f"Diff supplied at build/diff.patch (builder: {builder}); {note}")
                return True
            rec["status"] = "awaiting_builder"
            write_json(self.out / "needs_builder.json", {
                "run_id": self.run_id, "pipeline": self.spec["name"], "stage": rec["stage"], "step": step["id"],
                "builder": builder, "target": str(target), "plan": plan, "tests": tests,
                "constraints": [str(ROOT / c) for c in step.get("constraints") or []],
                "rule": "touch only files the plan names; make the red tests green; no other changes",
                "expected": str(manual_patch),
                "how": "write the code on the checkout, save `git diff` (staged + unstaged, new files included) to the "
                       "expected path, then re-run with --resume"})
            return False
        if builder == "claude-code":
            exe = shutil.which("claude")
            if not exe:
                raise StepError("builder claude-code: `claude` is not on PATH (install Claude Code, or use --builder manual with build/diff.patch)")
            if not is_git_root(target):
                raise StepError(f"builder claude-code: {target} is not a git repository root; the diff cannot be captured")
            prompt = self.agent_prompt(step, plan, tests)
            (sdir / "prompt.txt").write_text(prompt, encoding="utf-8")
            t0 = time.time()
            r = subprocess.run([exe, "-p", prompt, "--output-format", "text"], cwd=str(target), capture_output=True,
                               text=True, timeout=3600)
            rec["agent_exit"], rec["agent_duration_s"] = r.returncode, round(time.time() - t0, 3)
            (sdir / "agent-stderr.txt").write_text(r.stderr, encoding="utf-8")
            if r.returncode != 0:
                raise StepError(f"claude -p exited {r.returncode}: {r.stderr.strip().splitlines()[-1:] or ''}"[:300])
            git(target, "add", "-A")
            _, diff = git(target, "diff", "--cached", "--binary")
            patch = sdir / "captured.patch"
            patch.write_text(diff, encoding="utf-8")
            self._record_diff(patch, sdir, rec, plan, r.stdout)
            patch.unlink()
            return True
        raise StepError(f"unknown builder {builder!r}")

    def agent_prompt(self, step: dict, plan: str, tests: str) -> str:
        def body(p: str) -> str:
            t = Path(p).read_text(encoding="utf-8", errors="replace") if p and Path(p).is_file() else "(missing)"
            return t if len(t) <= CONTEXT_LIMIT else t[:CONTEXT_LIMIT] + "\n[... truncated ...]"
        parts = ["You are the build step of a delivery pipeline. Implement the plan below on this repository.",
                 "Rules: touch ONLY the files the plan names (plus the test files the test plan names); make the red tests "
                 "green; follow every constraint file; do not refactor, rename or reformat anything else; do not commit.",
                 "", "## Plan", "", body(plan), "", "## Test plan", "", body(tests)]
        for c in step.get("constraints") or []:
            parts += ["", f"## Constraint: {c}", "", body(str(ROOT / c))]
        parts += ["", "## Stack profile", "", json.dumps(self.record.get("stack_profile", {}), indent=2),
                  "", "When done, reply with a short summary: files changed and how each acceptance criterion is met."]
        return "\n".join(parts)

    def step_pr(self, step: dict, sdir: Path, rec: dict) -> None:
        title = self.subst(step.get("title", "")).strip() or f"deliver {self.run_id}"
        branch = self.subst(step.get("branch", "deliver/$run.id"))
        body = str(self.resolve(step.get("body", "$evidence"), "pr body"))
        rec.update(branch=branch, title=title)
        if self.args.dry:
            write_json(sdir / "pr.json", {"dry": True, "branch": branch, "title": title, "body": "evidence/EVIDENCE.md",
                                          "note": "dry run: no branch pushed, no pull request opened"})
            rec["exit"] = 0
            return
        if not shutil.which("gh"):
            raise StepError("pr step: `gh` is not on PATH (GitHub CLI is required to open the pull request; use --dry otherwise)")
        repo = self.repo
        if not is_git_root(repo):
            raise StepError(f"pr step: {repo} is not a git repository root")
        code, _ = git(repo, "rev-parse", "--verify", "-q", branch, ok=(0, 1))
        git(repo, "checkout", "-q", "-B" if code == 0 else "-b", branch)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "--allow-empty", "-m", title, "-m", f"Delivered by giri-skills pipeline {self.spec['name']} run {self.run_id}")
        git(repo, "push", "-u", "origin", branch)
        r = subprocess.run(["gh", "pr", "create", "--title", title, "--body-file", body, "--head", branch],
                           cwd=str(repo), capture_output=True, text=True)
        if r.returncode != 0:
            raise StepError(f"gh pr create: {(r.stderr or r.stdout).strip()[:300]}")
        v = subprocess.run(["gh", "pr", "view", branch, "--json", "number,url,headRefOid"], cwd=str(repo),
                           capture_output=True, text=True)
        info = json.loads(v.stdout) if v.returncode == 0 and v.stdout.strip() else {"url": r.stdout.strip()}
        write_json(sdir / "pr.json", {"dry": False, "branch": branch, "title": title, "number": info.get("number"),
                                      "url": info.get("url"), "head_sha": info.get("headRefOid")})
        rec["exit"] = 0

    # ---- gates
    def eval_gate(self, gate: dict, stage_rec: dict) -> tuple[str, str]:
        kind = gate.get("kind")
        steps = {s["id"]: s for s in stage_rec["steps"]}
        if kind == "output":
            s = steps.get(gate["step"])
            if not s or s.get("status") not in ("ok", "approved"):
                return "fail", f"step '{gate['step']}' did not complete"
            path = self.step_dirs[gate["step"]] / str(gate["file"])
            r = check_output.run_check(str(gate["check"]), str(path), mode=self.mode, out_dir=str(path.parent))
            return ("pass" if r["pass"] else "fail"), f"{gate['file']}: {gate['check']} — {r['evidence']}"
        if kind == "exit":
            s = steps.get(gate["step"])
            if not s or s.get("status") != "ok":
                return "fail", f"step '{gate['step']}' did not complete: {s.get('error', '') if s else 'not run'}"
            ok = s.get("exit") == 0
            return ("pass" if ok else "fail"), f"step '{gate['step']}' exit {s.get('exit')}" + ("" if ok else ": " + "; ".join(s.get("failed_checks") or ["see its report"]))
        if kind == "approval":
            s = steps.get(gate["step"])
            ok = bool(s and s.get("status") == "approved")
            return ("pass" if ok else "fail"), (f"approved by {s.get('approved_by')}" if ok else "not approved")
        if kind in ("all", "any"):
            results = [self.eval_gate(g, stage_rec) for g in gate.get("of") or []]
            verdicts = [v for v, _ in results]
            ok = all(v == "pass" for v in verdicts) if kind == "all" else any(v == "pass" for v in verdicts)
            return ("pass" if ok else "fail"), " | ".join(f"[{v}] {d}" for v, d in results)
        if kind == "external":
            return "recorded", f"satisfied outside the run: {gate.get('what', '')}"
        return "fail", f"unknown gate kind {kind!r}"

    # ---- evidence
    def write_evidence_md(self) -> None:
        rows = ["# Evidence", "", f"Pipeline `{self.spec['name']}` v{self.spec.get('version', '')} · run `{self.run_id}` · "
                f"mode {self.spec.get('mode', '')} · builder {self.args.builder} · provider {self.args.provider}"
                + (" · DRY RUN" if self.args.dry else ""), "",
                f"Request: {self.inputs.get('request', '')}", "",
                "Stack profile: " + ", ".join(f"{k}={v}" for k, v in (self.record.get("stack_profile") or {}).items()), "",
                "| Stage | Role | Gate | Verdict | Evidence |", "|---|---|---|---|---|"]
        for s in self.record.get("stages", []):
            g = s.get("gate") or {}
            ev = ", ".join(f"[{Path(p).name}]({p})" for p in s.get("evidence_files") or []) or "—"
            verdict = {"pass": "PASS", "fail": "FAIL", "recorded": "RECORDED"}.get(g.get("verdict", ""), s.get("status", "").upper())
            rows.append(f"| {s['id']} | {s['role']} | {g.get('kind', '')} | {verdict} | {ev} |")
        rows += ["", "Gate detail per stage is in `<stage>/gate.json`; step logs in `<stage>/<step>/`.", ""]
        (self.evidence / "EVIDENCE.md").write_text("\n".join(rows), encoding="utf-8")

    def hash_files(self) -> dict:
        files = {}
        for base in (self.evidence, self.out / "build"):
            if base.is_dir():
                for p in sorted(base.rglob("*")):
                    if p.is_file():
                        files[str(p.relative_to(self.out))] = sha256(p)
        return files

    def save(self, status: str, exit_code: int) -> None:
        self.record.update(status=status, exit_code=exit_code, finished_at=now())
        self.write_evidence_md()
        self.record["files"] = self.hash_files()
        write_json(self.out / "run.json", self.record)

    # ---- stages
    def run_stage(self, n: int, stage: dict, prev: dict | None, approvals: dict) -> tuple[str, int]:
        stage_dir = self.evidence / f"{n:02d}-{stage['id']}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        srec = {"id": stage["id"], "adlc_stage": stage.get("adlc_stage"), "role": stage.get("role"), "dir": str(stage_dir.relative_to(self.out)),
                "status": "running", "started_at": now(), "steps": []}
        done_steps = {s["id"]: s for s in (prev or {}).get("steps", []) if s.get("status") in ("ok", "approved")}
        t_stage = time.time()
        halted = ""
        for step in stage["steps"]:
            sid = step["id"]
            sdir = stage_dir / sid
            sdir.mkdir(parents=True, exist_ok=True)
            self.step_dirs[sid] = sdir
            if sid in done_steps:  # completed before this resume: keep its outputs and record
                rec = dict(done_steps[sid]); rec["resumed"] = True
                srec["steps"].append(rec)
                continue
            rec = {"id": sid, "kind": step.get("kind"), "stage": stage["id"], "status": "ok"}
            t0 = time.time()
            try:
                if halted:
                    rec.update(status="skipped", error=f"earlier step failed: {halted}")
                elif step["kind"] == "skill":
                    rec["skill"] = step["skill"]
                    self.step_skill(step, sdir, rec)
                elif step["kind"] == "compose":
                    rec["derive"] = step.get("derive")
                    self.step_compose(step, sdir, rec)
                elif step["kind"] == "approval":
                    if not self.step_approval(step, sdir, rec, approvals):
                        rec["duration_s"] = round(time.time() - t0, 3)
                        srec["steps"].append(rec)
                        srec.update(status="awaiting_approval", duration_s=round(time.time() - t_stage, 3))
                        srec["gate"] = {"verdict": "pending", "kind": stage["gate"]["kind"], "detail": f"waiting for approval of step '{sid}'",
                                        "role": stage.get("role"), "approved_by": "", "at": now()}
                        write_json(stage_dir / "gate.json", srec["gate"])
                        self._finish_stage(srec, stage)
                        return "awaiting_approval", EXIT_APPROVAL
                elif step["kind"] == "agent":
                    if not self.step_agent(step, sdir, rec):
                        rec["duration_s"] = round(time.time() - t0, 3)
                        srec["steps"].append(rec)
                        srec.update(status="awaiting_builder", duration_s=round(time.time() - t_stage, 3))
                        srec["gate"] = {"verdict": "pending", "kind": stage["gate"]["kind"], "detail": f"waiting for the builder at step '{sid}'",
                                        "role": stage.get("role"), "approved_by": "", "at": now()}
                        write_json(stage_dir / "gate.json", srec["gate"])
                        self._finish_stage(srec, stage)
                        return "awaiting_builder", EXIT_BUILDER
                elif step["kind"] == "pr":
                    self.step_pr(step, sdir, rec)
                else:
                    raise StepError(f"unknown step kind {step.get('kind')!r}")
            except StepError as e:
                rec.update(status="failed", error=str(e)[:400])
                halted = f"{sid}: {e}"
            except subprocess.TimeoutExpired:
                rec.update(status="failed", error="timed out")
                halted = f"{sid}: timed out"
            rec["duration_s"] = round(time.time() - t0, 3)
            srec["steps"].append(rec)
        verdict, detail = self.eval_gate(stage["gate"], srec)
        if halted and verdict != "fail":
            verdict, detail = "fail", f"step failed — {halted}"
        approved = next((s.get("approved_by", "") for s in srec["steps"] if s.get("status") == "approved"), "")
        srec["gate"] = {"verdict": verdict, "kind": stage["gate"]["kind"], "detail": detail, "role": stage.get("role"),
                        "approved_by": approved, "at": now()}
        write_json(stage_dir / "gate.json", srec["gate"])
        srec["status"] = "passed" if verdict in ("pass", "recorded") else "failed"
        srec["duration_s"] = round(time.time() - t_stage, 3)
        self._finish_stage(srec, stage)
        return srec["status"], (EXIT_OK if srec["status"] == "passed" else EXIT_FAIL)

    def _finish_stage(self, srec: dict, stage: dict) -> None:
        files = []
        for ref in stage.get("evidence") or []:
            try:
                p = Path(str(self.resolve(ref, "evidence")))
                if p.is_file():
                    files.append(str(p.relative_to(self.evidence)))
            except StepError:
                continue
        srec["evidence_files"] = files
        stages = self.record.setdefault("stages", [])
        for i, s in enumerate(stages):
            if s["id"] == srec["id"]:
                stages[i] = srec
                break
        else:
            stages.append(srec)


# ------------------------------------------------------------------ main

def load_pipeline(arg: str) -> tuple[dict, Path]:
    p = Path(arg)
    if not p.is_file():
        p = ROOT / "pipelines" / f"{arg}.json"
    if not p.is_file():
        sys.exit(f"error: pipeline not found: {arg} (a name under pipelines/ or a path)")
    return read_json(p), p


def load_approvals(path: str | None) -> dict:
    if not path:
        return {}
    data = read_json(Path(path))
    items = data.get("approvals") if isinstance(data, dict) and isinstance(data.get("approvals"), list) else None
    if items is None and isinstance(data, dict):
        return {k: (v if isinstance(v, dict) else {"by": str(v)}) for k, v in data.items()}
    return {str(a.get("step")): a for a in (items or []) if isinstance(a, dict) and a.get("step")}


def baseline_commit(repo: Path) -> None:
    """Dry copies only: give a commit-less repo one baseline commit (fixed identity and date), so skills that read
    git history (handoff) have something to read. A repo that already has commits is left as it is."""
    if not shutil.which("git") or not is_git_root(repo):
        return
    code, _ = git(repo, "rev-parse", "--verify", "-q", "HEAD", ok=(0, 1))
    if code == 0:
        return
    git(repo, "add", "-A")
    _, out = git(repo, "status", "--porcelain")
    if out.strip():
        git(repo, "commit", "-q", "-m", "baseline: working copy for a dry delivery run")


def prepare_repo(run: Run) -> None:
    src = Path(run.inputs["repo"]).expanduser()
    if run.args.dry:
        work = run.out / "repo"
        if not work.exists():
            if src.is_dir():
                shutil.copytree(src, work, ignore=COPY_IGNORE, symlinks=True)
            else:
                work.mkdir(parents=True)
        run.repo = work.resolve()
        if not is_git_root(run.repo) and shutil.which("git"):
            git(run.repo, "init", "-q")
        baseline_commit(run.repo)
        return
    if not src.is_dir():
        if run.spec.get("mode") == "greenfield":
            src.mkdir(parents=True, exist_ok=True)
        else:
            sys.exit(f"error: --repo {src} is not a directory")
    run.repo = src.resolve()
    if run.inputs.get("ref") and is_git_root(run.repo):
        git(run.repo, "checkout", "-q", str(run.inputs["ref"]))


def build_args(argv=None):
    ap = argparse.ArgumentParser(description="Run a delivery pipeline against a repository (see docs/DELIVERY-PIPELINES.md)")
    ap.add_argument("pipeline", help="pipeline name under pipelines/ or a path to its JSON")
    ap.add_argument("--repo", help="target repository (local checkout, or the directory to create for greenfield)")
    ap.add_argument("--request", help="the request in the requester's words")
    ap.add_argument("--brief", help="product brief JSON (optional)")
    ap.add_argument("--ref", help="branch or commit to start from")
    ap.add_argument("--input", action="append", default=[], metavar="NAME=VALUE", help="any other pipeline input (e.g. name=… for greenfield)")
    ap.add_argument("--out", required=True, help="run directory (evidence/, run.json, build/)")
    ap.add_argument("--builder", choices=["none", "manual", "claude-code"], default="none")
    ap.add_argument("--provider", choices=["dry", "none", "anthropic", "openai"], default="dry")
    ap.add_argument("--approve-all", action="store_true", help="satisfy every approval step (the invoker approves)")
    ap.add_argument("--approvals", help="JSON file recording approvals: {\"approvals\": [{\"step\": id, \"by\": name, \"note\": ...}]}")
    ap.add_argument("--patch", help="copy this diff to <out>/build/diff.patch before running (manual builder)")
    ap.add_argument("--dry", action="store_true", help="work on a copy of the repo under <out>/repo; the pr step opens nothing")
    ap.add_argument("--resume", action="store_true", help="continue an existing run from the first incomplete stage")
    ap.add_argument("--run-id", help="run id (default: derived from pipeline + request + repo, with a time suffix outside --dry)")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = build_args(argv)
    spec, spec_path = load_pipeline(args.pipeline)
    problems = vp.validate_pipeline(spec, vp.load_context(), spec_path.name)
    if problems:
        print(f"error: pipeline {spec_path.name} is invalid:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return EXIT_ARGS
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    run = Run(spec, args, out)
    run.evidence.mkdir(exist_ok=True)
    prev_record = read_json(out / "run.json") if (out / "run.json").is_file() else None
    if prev_record and not args.resume:
        print(f"error: {out / 'run.json'} exists — pass --resume to continue it or use a new --out", file=sys.stderr)
        return EXIT_ARGS
    if args.resume and not prev_record:
        print(f"error: --resume but {out / 'run.json'} does not exist", file=sys.stderr)
        return EXIT_ARGS

    # inputs
    given = {}
    for it in args.input:
        if "=" not in it:
            print(f"error: --input expects name=value, got {it!r}", file=sys.stderr)
            return EXIT_ARGS
        k, _, v = it.partition("=")
        given[k.strip()] = v
    for k in ("repo", "request", "brief", "ref"):
        v = getattr(args, k)
        if v:
            given[k] = v
    if prev_record:
        for k, v in (prev_record.get("inputs") or {}).items():
            given.setdefault(k, v)
    declared = {i["name"]: i for i in spec.get("inputs") or []}
    unknown = sorted(k for k in given if k not in declared)
    if unknown:
        print(f"error: unknown input(s) {unknown}; the pipeline declares {sorted(declared)}", file=sys.stderr)
        return EXIT_ARGS
    missing = [n for n, i in declared.items() if i.get("required") and not str(given.get(n, "")).strip()]
    for n in list(given):
        if declared[n]["type"] in ("json", "md", "csv", "file", "dir") and given[n] and not Path(given[n]).expanduser().is_file() and not Path(given[n]).expanduser().is_dir():
            print(f"error: input '{n}' file not found: {given[n]}", file=sys.stderr)
            return EXIT_ARGS
        if declared[n]["type"] in ("json", "md", "csv", "file", "dir"):
            given[n] = str(Path(given[n]).expanduser().resolve())
    if missing:
        write_json(out / "needs_input.json", {"pipeline": spec["name"], "missing": [
            {"name": n, "type": declared[n]["type"], "from": declared[n].get("from", "")} for n in missing]})
        print("needs input: " + ", ".join(f"--{n}" if n in ("repo", "request", "brief", "ref") else f"--input {n}=…" for n in missing), file=sys.stderr)
        return EXIT_ARGS
    run.inputs = given
    repo_key = str(Path(given["repo"]).expanduser())
    if prev_record:
        run.run_id = prev_record["run_id"]
    else:
        base = hashlib.sha256(f"{spec['name']}|{given.get('request', '')}|{repo_key}".encode()).hexdigest()[:10]
        run.run_id = args.run_id or (base if args.dry else f"{base}-{int(time.time())}")
    if args.patch:
        (out / "build").mkdir(exist_ok=True)
        shutil.copy(args.patch, out / "build" / "diff.patch")
    approvals = load_approvals(args.approvals)

    run.record = {"run_id": run.run_id, "pipeline": spec["name"], "version": spec.get("version", ""), "mode": spec.get("mode", ""),
                  "dry": bool(args.dry), "builder": args.builder, "provider": args.provider, "inputs": given,
                  "repo_input": repo_key, "out": str(out), "started_at": (prev_record or {}).get("started_at") or now(),
                  "resumed": bool(prev_record), "stages": list((prev_record or {}).get("stages") or [])}
    try:
        prepare_repo(run)
    except StepError as e:
        print(f"error: {e}", file=sys.stderr)
        run.save("failed", EXIT_FAIL)
        return EXIT_FAIL
    run.record["repo"] = str(run.repo)

    prev_stages = {s["id"]: s for s in run.record["stages"]}
    # restore step dirs of stages already passed (references into them must resolve on resume)
    for n, stage in enumerate(spec["stages"], 1):
        for step in stage["steps"]:
            run.step_dirs[step["id"]] = run.evidence / f"{n:02d}-{stage['id']}" / step["id"]
    profile_after = (spec.get("stack_profile") or {}).get("after")
    try:
        if not profile_after or prev_stages.get(profile_after, {}).get("status") == "passed":
            run.read_profile()
        elif (run.evidence / "stack-profile.json").is_file():
            run.profile = read_json(run.evidence / "stack-profile.json")
    except StepError as e:
        print(f"error: {e}", file=sys.stderr)
        run.save("failed", EXIT_FAIL)
        return EXIT_FAIL
    for n, stage in enumerate(spec["stages"], 1):
        prev = prev_stages.get(stage["id"])
        if prev and prev.get("status") == "passed":
            continue
        status, code = run.run_stage(n, stage, prev, approvals)
        run.save(status, code)
        if code != EXIT_OK:
            where = {EXIT_APPROVAL: f"needs approval — see {out / 'needs_approval.json'}",
                     EXIT_BUILDER: f"needs the builder — see {out / 'needs_builder.json'}"}.get(code, "gate failed — see " + str(run.evidence / f"{n:02d}-{stage['id']}" / "gate.json"))
            print(f"{spec['name']} run {run.run_id}: stopped at stage '{stage['id']}' ({status}): {where}")
            return code
        if profile_after == stage["id"]:
            try:
                if args.dry:
                    baseline_commit(run.repo)
                run.read_profile()
            except StepError as e:
                print(f"error: {e}", file=sys.stderr)
                run.save("failed", EXIT_FAIL)
                return EXIT_FAIL
        print(f"  stage {stage['id']}: {status} — {run.record['stages'][-1]['gate']['detail'][:120]}")
    run.save("passed", EXIT_OK)
    print(f"{spec['name']} run {run.run_id}: {len(spec['stages'])} stages passed — evidence in {run.evidence / 'EVIDENCE.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
