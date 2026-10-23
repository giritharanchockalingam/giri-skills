#!/usr/bin/env python3
"""Run a delivery pipeline (pipelines/<name>.json) against a real repository — docs/DELIVERY-PIPELINES.md.

    python3 scripts/deliver.py feature-delivery --repo ./app --request "Export orders as CSV" \
        [--brief brief.json] [--ref main] [--input name=value ...] --out ./runs/r1 \
        --builder none|manual|claude-code [--provider dry|none|anthropic|openai] \
        [--approve-all | --approvals approvals.json] [--patch diff.patch] [--files files.txt] [--plan DIR] [--dry] [--resume] [--run-id ID] \
        [--no-baseline] \
        [--run <portal run uuid> --portal https://<studio> [--approval-timeout 3600] [--poll-interval 30]]

`--pipeline <name>` is an alias of the positional. With --run and --portal (API key in env SF_API_KEY) the executor
posts one stage record (studio DeliveryStageInput) to <portal>/api/delivery-runs/<run>/stage after the stack profile
and after every stage — including approval waits, builder waits, gate failures and the final stage — with the
stack profile on the first post, the PR on the stage that opened it, the evidence hashes of the stage and the
executor_ref (GITHUB_RUN_URL, or GITHUB_SERVER_URL/GITHUB_REPOSITORY/actions/runs/GITHUB_RUN_ID). A post that
fails is retried 3x with backoff, logged to <out>/callback.log and never aborts the run. An approval step then polls
GET <portal>/api/delivery-runs/<run> every --poll-interval seconds (up to --approval-timeout) until the portal
records an approval for that stage, so a portal approval resumes a CI run; --approve-all or --approvals skip the poll.

Order of work: the stack profile (scripts/stack_profile.py, once, before stage 1 — or after the stage the
pipeline's `stack_profile.after` names), then the stages in order. Step kinds:
  skill     scripts/run_skill.py in a subprocess, inputs resolved from references; an optional input that
            resolves to nothing is omitted; `gate: true` means exit 1 fails the stage at once
  compose   a deterministic derivation (brief-from-request, spec-from-prd, feature-from-plan)
  approval  blocks: needs_approval.json is written and the run exits 3, unless --approve-all or the
            --approvals file records the step ({"approvals": [{"step": "<id>", "by": "...", "note": "..."}]})
  agent     the code step (no `produces`):
            --builder none        -> needs_builder.json, exit 4: a person or IDE agent writes the code and
                                     drops the diff at <out>/build/diff.patch, then re-runs with --resume
            --builder manual      -> <out>/build/diff.patch must exist; it is recorded and, outside --dry, applied to the
                                     checkout with `git apply --index` so the later gates and the pr step see the change
                                     (refused with exit 1 when it touches files outside files.txt + test paths or does
                                     not apply cleanly; a diff the checkout already carries is skipped — idempotent on
                                     --resume); evidence: <step>/applied.json (files, git diff --stat)
            --builder claude-code -> `claude -p` on the checkout with a prompt built from the plan, the test
                                     plan, files.txt and the constraint files; `git diff` is captured as diff.patch
            the files step (`produces: ["files.txt"]`): the files the change will touch, one repo-relative
            path per line. When tasks.csv names files for every task the executor derives files.txt itself
            (no builder). Otherwise --builder none stops with needs_builder.json (exit 4) naming the path
            <out>/evidence/<nn>-build/files/files.txt (or <out>/build/files.txt, where --files copies to);
            --builder manual expects it there; --builder claude-code prompts `claude -p` to write it.
            the plan-refine step (`produces: ["plan.md", "tasks.csv"]`, architecture stage): the architect turns the
            spec-to-plan scaffold into a complete plan — file table filled, every task with acceptance, test,
            rollback and files (repo-relative, create/modify per the checkout), nothing invented beyond the PRD and
            the request. A scaffold that is already complete (no TBD in acceptance/test/files, every task names
            files) is taken as is: the step is skipped deterministically and the scaffold copied into the step
            folder. Otherwise --builder none|manual stops with needs_builder.json (exit 4) naming both expected
            paths <out>/evidence/<nn>-architecture/plan-refine/{plan.md,tasks.csv} (or <out>/build/plan/, where
            --plan DIR copies to); --builder claude-code prompts `claude -p` to write them. The stage gate then
            checks the refined tasks.csv (files and acceptance non-empty, no [TO BE BASELINED cell in acceptance,
            test or files) BEFORE anyone is asked to approve: an incomplete plan fails the stage (exit 1), it is
            never put in front of an approver.
  pr        --dry writes pr.json {"dry": true}; otherwise: branch deliver/<run-id> on the checkout, the checkout's
            changes committed as skills-factory[bot], pushed to origin (`gh auth setup-git` first when GH_TOKEN is
            set), then `gh pr create --title … --body-file EVIDENCE.md` run with cwd = the checkout
Gates per the doc (output / exit / approval / all / any / external). A failed gate stops the run with exit 1
and the evidence so far.

Brownfield baselines (the gate rule is "no NEW high findings from this change", never "the repo is clean"):
before the build stage's code step applies anything, the executor runs every baseline-accepting skill a later
step uses (nextjs-enterprise-conventions, perf-review-runner, ui-component-quality, tech-debt-audit-runner)
against the pre-change tree — deterministic, provider none — and stores
<out>/evidence/00-baseline/<skill>/{findings.csv,report.md}. `$profile.baselines.<check>` then resolves to that
findings.csv when the stack profile records none (a baseline recorded in the repo, docs/baselines/<check>-findings.csv,
still wins). The pre-change tree is `git archive` of the recorded base commit (run.json `base_sha`: HEAD when the run
started; the change stays uncommitted until the pr step, so HEAD is pre-change) into <out>/baseline-repo — never the
working copy, no stash. A run resumed at any stage at or past the code step with no baseline yet takes it first.
EVIDENCE.md carries a Baseline row (findings per check before the change) and run.json `baseline`. A gate that fails
on new high findings names the full count, the first 10 and "… and M more". --no-baseline skips all of it (every
finding is then new); greenfield pipelines have nothing to baseline.

Evidence bundle under <out>/evidence/: stack-profile.json, 00-baseline/ (see above), one folder per stage
(<nn>-<stage>/<step>/… outputs and gate.json) and EVIDENCE.md (the table that goes into the PR body). <out>/run.json records stages, steps,
exit codes, durations and the sha256 of every evidence file. --dry works on a copy of the repo under
<out>/repo (git-initialised with a fixed identity, so the run is reproducible); otherwise the checkout is used
in place. --resume continues an existing <out> from the first incomplete stage (completed steps are kept).

Exit codes: 0 every stage passed · 1 a gate or step failed · 2 bad arguments / missing pipeline input
(needs_input.json) / pipeline wiring error — a step input no earlier step produced (wiring_error.json, never a
gate failure) · 3 waiting for an approval (needs_approval.json) · 4 waiting for the builder (needs_builder.json).
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
import tarfile
import time
import urllib.error
import urllib.request
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
# The pr step commits on the real checkout as the factory bot (real dates; the user's git config and the credential
# helper `gh auth setup-git` installs stay visible, which GIT_ENV hides on purpose for the dry copy).
BOT_NAME, BOT_EMAIL = "skills-factory[bot]", "skills-factory[bot]@users.noreply.github.com"
BOT_GIT_ENV = {"GIT_AUTHOR_NAME": BOT_NAME, "GIT_AUTHOR_EMAIL": BOT_EMAIL,
               "GIT_COMMITTER_NAME": BOT_NAME, "GIT_COMMITTER_EMAIL": BOT_EMAIL}
CALLBACK_RETRIES = 3
CALLBACK_BACKOFF = float(os.environ.get("SF_CALLBACK_BACKOFF", "1") or 0)   # seconds; doubles per retry
STAGE_STATUS = {"passed": "succeeded", "failed": "blocked", "awaiting_approval": "awaiting_approval",
                "awaiting_builder": "blocked", "wiring_error": "blocked", "running": "running"}
FILES_TXT = "files.txt"
PLAN_MD, TASKS_CSV = "plan.md", "tasks.csv"
PLAN_FILES = (PLAN_MD, TASKS_CSV)                   # what the plan-refine step produces (see step_plan_refine)
PLAN_COLUMNS = ["id", "task", "acceptance", "test", "rollback", "files", "size", "repo_check"]   # spec-to-plan's tasks.csv
PLAN_FILLED = ("acceptance", "test", "files")       # a scaffold is complete when none of these is TBD or empty in any task
# skills whose `baseline` input is a findings.csv of recorded debt, and the stack-profile check each one is wired from
BASELINE_SKILLS = {"build/nextjs-enterprise-conventions": "nextjs", "build/perf-review-runner": "perf",
                   "build/ui-component-quality": "ui", "build/tech-debt-audit-runner": "debt"}
BASELINE_DIR = "00-baseline"                        # <out>/evidence/00-baseline/<skill>/findings.csv — the pre-change findings
NEW_HIGH_LISTED = 10                                # gate detail: the full count, the first 10 findings, "… and M more"
GATE_DETAIL_LIMIT = 1200                            # the count comes first, so a long list never hides it
TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|e2e)/")   # test files the code step may add beside files.txt


class StepError(Exception):
    pass


def new_high_detail(count: int, listed: list[str]) -> str:
    """'N new high finding(s) against the baseline: a; b; … and M more' — the count is always the real total."""
    shown = listed[:NEW_HIGH_LISTED]
    more = count - len(shown)
    return (f"{count} new high finding(s) against the baseline: " + "; ".join(shown)
            + (f" … and {more} more" if more > 0 else ""))


class WiringError(StepError):
    """A step input that no earlier step produced: the pipeline is mis-wired (exit 2), not a gate verdict."""

    def __init__(self, step: str, inp: str, detail: str, skill: str = ""):
        self.step, self.input, self.skill, self.detail = step, inp, skill, detail
        super().__init__(f"pipeline wiring error: step '{step}' input '{inp}' {detail}")



def repo_path(s: str) -> str:
    """A path cell as the plan or files.txt writes it → repo-relative: backticks and a `./` prefix dropped, backslashes
    normalised. A dotfile keeps its dot (`.env.example`): str.lstrip("./") ate it and the code step then refused the
    diff that touched it (first real run)."""
    return re.sub(r"^(?:\./)+", "", s.strip().strip("`").replace("\\", "/"))

def read_files_txt(path: Path) -> list[str]:
    """files.txt: one repo-relative path per line; blank lines and `#` comments ignored; order kept, duplicates dropped."""
    out: list[str] = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        s = repo_path(s)
        if s and s not in out:
            out.append(s)
    return out


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def to_utc(local: str | None) -> str | None:
    """A now() timestamp (local, no offset) as RFC 3339 UTC — what the portal's stage schema accepts."""
    if not local:
        return None
    try:
        t = time.mktime(time.strptime(local, "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def executor_ref() -> str:
    """Where this run executes, when GitHub Actions says so (GITHUB_RUN_URL, or the server/repo/run id triple)."""
    env = os.environ
    if env.get("GITHUB_RUN_URL"):
        return env["GITHUB_RUN_URL"][:400]
    if env.get("GITHUB_SERVER_URL") and env.get("GITHUB_REPOSITORY") and env.get("GITHUB_RUN_ID"):
        return f"{env['GITHUB_SERVER_URL'].rstrip('/')}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"[:400]
    return ""


class Portal:
    """The portal callback (docs/DELIVERY-PIPELINES.md → Where it runs): POST stage records, GET the run for
    approvals. Stdlib urllib; every attempt is logged to <out>/callback.log; a failed post never aborts the run."""

    def __init__(self, base: str, run_id: str, api_key: str, log: Path):
        self.base, self.run_id, self.api_key, self.log = base.rstrip("/"), run_id, api_key, log
        self.posts = 0

    def _log(self, line: str) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a", encoding="utf-8") as f:
            f.write(f"{now()} {line}\n")

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[int, str]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json",
                                              **({"Content-Type": "application/json"} if data else {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")[:300]
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            return 0, str(getattr(e, "reason", e))[:300]

    def post_stage(self, record: dict) -> bool:
        path = f"/api/delivery-runs/{self.run_id}/stage"
        self.posts += 1
        for attempt in range(1, CALLBACK_RETRIES + 1):
            status, text = self._request("POST", path, record)
            if 200 <= status < 300:
                self._log(f"POST {path} stage={record['id']} status={record['status']} -> {status}")
                return True
            self._log(f"POST {path} stage={record['id']} status={record['status']} attempt {attempt}/{CALLBACK_RETRIES} failed: "
                      f"HTTP {status} {text.strip()[:200]}")
            if 400 <= status < 500 and status != 429:
                break  # the portal rejected the record: retrying the same body cannot help
            if attempt < CALLBACK_RETRIES:
                time.sleep(CALLBACK_BACKOFF * (2 ** (attempt - 1)))
        print(f"warning: portal callback failed for stage '{record['id']}' ({record['status']}) — see {self.log}", file=sys.stderr)
        return False

    def get_run(self) -> dict | None:
        status, text = self._request("GET", f"/api/delivery-runs/{self.run_id}")
        if 200 <= status < 300:
            try:
                data = json.loads(text)
                return data if isinstance(data, dict) else None
            except ValueError:
                self._log(f"GET run: not JSON ({text[:80]!r})")
                return None
        self._log(f"GET run failed: HTTP {status} {text.strip()[:200]}")
        return None

    def approval_for(self, stage_id: str) -> dict | None:
        run = self.get_run()
        for a in (run or {}).get("approvals") or []:
            if isinstance(a, dict) and a.get("stage_id") == stage_id:
                return a
        return None


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def git(repo: Path, *args: str, ok=(0,), env: dict | None = None) -> tuple[int, str]:
    r = subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=str(repo), capture_output=True, text=True,
                       env={**os.environ, **(GIT_ENV if env is None else env)})
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
        self.portal: Portal | None = None
        self.profile_posted = False
        self.baseline: dict = {}          # run.json `baseline`: {status, target, checks: {check: {skill, source, findings, high, path}}}

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
            if m.group(1) == "baselines" and m.group(2) and not v:
                v = self.baseline_path(m.group(2))   # the profile records none: the pre-change findings this run captured
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
            if key in vp.TEXT_MODIFIERS:   # `#csv` / `#lines` on a text file such as files.txt
                lines = read_files_txt(path)
                return ",".join(lines) if key == "csv" else "\n".join(lines)
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

    # ---- brownfield baselines (docs/DELIVERY-PIPELINES.md → Stack profile and baselines)
    def baseline_path(self, check: str) -> str:
        """The findings.csv this run captured for a check before the change, or "" when there is none."""
        info = (self.baseline.get("checks") or {}).get(check) or {}
        p = self.out / info["path"] if info.get("source") == "captured" and info.get("path") else None
        return str(p) if p and p.is_file() else ""

    def load_baseline(self) -> None:
        """A resume: the baseline captured by the earlier run is read back, never re-run on a changed checkout."""
        bj = self.evidence / BASELINE_DIR / "baseline.json"
        if bj.is_file():
            self.baseline = read_json(bj)
            self.record["baseline"] = self.baseline

    def _baseline_steps(self, stages: list[dict], from_stage: int, after_step: str) -> list[dict]:
        """Skill steps later in the pipeline that take a baseline findings.csv, one per skill (first wiring wins)."""
        seen, out = set(), []
        for i, st in enumerate(stages):
            if i < from_stage:
                continue
            passed = i > from_stage
            for step in st["steps"]:
                if i == from_stage and not passed:
                    passed = step["id"] == after_step
                    continue
                skill = step.get("skill", "")
                if step.get("kind") == "skill" and skill in BASELINE_SKILLS and "baseline" in (step.get("inputs") or {}) and skill not in seen:
                    seen.add(skill)
                    out.append(step)
        return out

    def _baseline_target(self) -> tuple[Path, str]:
        """The pre-change tree, never the working copy: the recorded base commit (run.json `base_sha`, HEAD when the
        run started — the change is applied uncommitted, so HEAD stays pre-change until the pr step commits it)
        exported with `git archive` into <out>/baseline-repo. No git / no commit yet: the checkout itself, provided
        it is clean. No stash, nothing on the checkout is touched."""
        repo = self.repo
        if not shutil.which("git") or not is_git_root(repo):
            return repo, "the checkout (not a git repository)"
        code, head = git(repo, "rev-parse", "--verify", "-q", "HEAD", ok=(0, 1))
        if code != 0:
            return repo, "the checkout (no commit yet)"
        base = str(self.record.get("base_sha") or "").strip() or head.strip()
        export = self.out / "baseline-repo"
        if export.exists():
            shutil.rmtree(export)
        export.mkdir(parents=True)
        r = subprocess.run(["git", "-c", "commit.gpgsign=false", "archive", "--format=tar", base], cwd=str(repo),
                           capture_output=True, env={**os.environ, **GIT_ENV})
        if r.returncode != 0:
            raise StepError(f"baseline: git archive {base[:12]}: {r.stderr.decode('utf-8', 'replace').strip()[:200]}")
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
            tar.extractall(export, filter="data") if hasattr(tarfile, "data_filter") else tar.extractall(export)
        which = "HEAD" if base == head.strip() else f"the recorded base commit {base[:12]}"
        return export, f"git archive {which} (the pre-change tree; the checkout itself is never linted for the baseline)"

    def code_step_index(self) -> tuple[int, dict | None]:
        """(stage index, step) of the code step — the agent step with no `produces` — or (-1, None)."""
        for i, st in enumerate(self.spec["stages"]):
            for step in st["steps"]:
                if step.get("kind") == "agent" and not (step.get("produces") or []):
                    return i, step
        return -1, None

    def ensure_baseline(self, stage_index: int) -> None:
        """A stage at or after the code step's is about to run and no baseline exists (a resume at a later step, or a
        run started before baselines existed): take it now — always from the pre-change tree, never the checkout."""
        if self.baseline.get("status"):
            return
        ci, code_step = self.code_step_index()
        if code_step is None or stage_index < ci:
            return
        self.capture_baseline(ci, code_step)

    @staticmethod
    def _count_findings(path: Path) -> tuple[int, int]:
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
        rows = [r for r in rows if (r.get("rule") or "").strip() and not (r.get("rule") or "").startswith("#")]
        return len(rows), sum(1 for r in rows if (r.get("severity") or "").strip() == "high")

    def capture_baseline(self, stage_index: int, code_step: dict) -> None:
        """Before the code step changes anything: run every baseline-accepting skill a later step uses against the
        untouched code (provider none, deterministic) into evidence/00-baseline/<skill>/, so the gates later compare
        against it. A check the stack profile already records (docs/baselines/<check>-findings.csv) is counted, not
        re-captured — the profile wins. Idempotent: an existing baseline.json (a resume) is kept."""
        if self.baseline.get("status"):
            return
        bdir = self.evidence / BASELINE_DIR
        base = {"dir": str(bdir.relative_to(self.out)), "at": now(), "checks": {}}
        steps = self._baseline_steps(self.spec["stages"], stage_index, code_step["id"])
        if self.args.no_baseline:
            base.update(status="skipped", reason="--no-baseline: every finding of the gate skills is new")
        elif self.spec.get("mode") == "greenfield":
            base.update(status="skipped", reason="greenfield: the repository is created by this run, there is nothing before the change")
        elif not steps:
            base.update(status="none", reason="no later step takes a baseline")
        else:
            target, how = self._baseline_target()
            base.update(status="captured", target=str(target), target_source=how)
            for step in steps:
                skill = step["skill"]
                check = BASELINE_SKILLS[skill]
                recorded = (self.profile.get("baselines") or {}).get(check)
                if recorded and Path(str(recorded)).is_file():
                    n, high = self._count_findings(Path(str(recorded)))
                    base["checks"][check] = {"skill": skill, "source": "profile", "path": str(recorded), "findings": n, "high": high,
                                             "note": "recorded in the repository (docs/baselines); the profile wins"}
                    continue
                sdir = bdir / skill.rsplit("/", 1)[-1]
                sdir.mkdir(parents=True, exist_ok=True)
                argv = [sys.executable, "-I", str(HERE / "run_skill.py"), skill, "--out", str(sdir), "--provider", "none",
                        "--input", f"target={target}"]
                for k, v in (step.get("inputs") or {}).items():
                    if k in ("target", "baseline"):
                        continue
                    val = self.resolve(v, f"baseline {skill} input '{k}'") if not (isinstance(v, str) and vp.STEP_REF.match(v)) else ""
                    if val is not None and str(val) != "":
                        argv += ["--input", f"{k}={val}"]
                t0 = time.time()
                r = subprocess.run(argv, capture_output=True, text=True, cwd=str(ROOT), timeout=1800)
                (sdir / "deliver-step.log").write_text(r.stdout + r.stderr, encoding="utf-8")
                findings = sdir / "findings.csv"
                entry = {"skill": skill, "source": "captured", "exit": r.returncode, "duration_s": round(time.time() - t0, 3),
                         "path": str(findings.relative_to(self.out)), "report": str((sdir / "report.md").relative_to(self.out))}
                if r.returncode >= 2:
                    raise StepError(f"baseline {skill} failed (exit {r.returncode}): "
                                    f"{(r.stderr or r.stdout).strip().splitlines()[-1:] or ['']}"[:300])
                if findings.is_file():
                    entry["findings"], entry["high"] = self._count_findings(findings)
                else:
                    entry.update(source="error", path="", findings=None, high=None,
                                 error=f"{skill} wrote no findings.csv (exit {r.returncode}): the gate runs without a baseline, every finding is new")
                base["checks"][check] = entry
        self.baseline = base
        self.record["baseline"] = base
        write_json(bdir / "baseline.json", base)

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
            missing = [str(m.get("name")) for m in read_json(ni).get("missing", [])] if ni.is_file() else []
            declared = step.get("inputs") or {}
            name = next((n for n in missing if n), "?")
            src = declared.get(name)
            detail = (f"resolved to nothing from {src!r}: no earlier step produced it (skill {step['skill']} requires it)" if src
                      else f"is required by skill {step['skill']} but the pipeline does not wire it")
            raise WiringError(step["id"], name, detail, step["skill"])
        if r.returncode >= 3:
            tail = (r.stderr or r.stdout).strip().splitlines()
            raise StepError(f"skill {step['skill']} failed (exit {r.returncode}): {tail[-1] if tail else ''}"[:300])
        fcsv = sdir / "findings.csv"
        if fcsv.is_file():   # the lint skills: what is new against the baseline is what the gate judges
            rows = [row for row in csv.DictReader(io.StringIO(fcsv.read_text(encoding="utf-8-sig")))
                    if (row.get("rule") or "").strip() and not (row.get("rule") or "").startswith("#")]
            rec["findings"] = len(rows)
            rec["known"] = sum(1 for row in rows if (row.get("status") or "") == "known")
            new_high = [f"{row['rule']} {row.get('file', '')}:{row.get('line', '')}" for row in rows
                        if (row.get("severity") or "") == "high" and (row.get("status") or "new") != "known"]
            rec["new_high_count"] = len(new_high)
            rec["new_high"] = new_high[:NEW_HIGH_LISTED]
        if r.returncode == 1 and step.get("gate"):
            why = (new_high_detail(rec["new_high_count"], rec["new_high"]) if rec.get("new_high_count")
                   else "; ".join(rec.get("failed_checks") or ["see report"]))
            raise StepError(f"gate step {step['skill']} said no (exit 1): {why}"[:GATE_DETAIL_LIMIT])

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
        if ap is None and self.portal and not self.args.approvals:
            ap = self.poll_approval(step, rec)
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

    def poll_approval(self, step: dict, rec: dict) -> dict | None:
        """Portal mode: tell the portal the stage waits, then poll the run until a person approves this stage
        there (or --approval-timeout passes, when the run stops with exit 3 as it would without a portal)."""
        stage_id = rec["stage"]
        self.post_stage({"id": stage_id, "status": "awaiting_approval",
                         "gate": {"kind": "approval", "verdict": "pending", "detail": f"waiting for approval of step '{step['id']}' ({step.get('role', '')})"}},
                        started_at=getattr(self, "stage_started", None))
        deadline = time.time() + max(0.0, float(self.args.approval_timeout))
        print(f"  waiting for approval of '{step['id']}' in the portal (stage {stage_id}, up to {int(self.args.approval_timeout)} s)")
        polls = 0
        while True:
            a = self.portal.approval_for(stage_id)
            polls += 1
            if a:
                rec["polls"] = polls
                return {"by": str(a.get("approved_by", "")), "note": str(a.get("note", "")), "portal_approval_id": a.get("id", "")}
            if time.time() >= deadline:
                rec["polls"] = polls
                self.portal._log(f"approval poll for stage {stage_id} timed out after {polls} polls")
                return None
            time.sleep(max(0.0, min(float(self.args.poll_interval), deadline - time.time())))

    def _plan_files(self, plan_path: str) -> list[str]:
        text = Path(plan_path).read_text(encoding="utf-8", errors="replace") if plan_path and Path(plan_path).is_file() else ""
        files = set()
        for m in re.finditer(r"^\s*-\s*Files:\s*(.+)$", text, re.M):  # spec-to-plan task blocks: "- Files: a,b"
            files |= {f.strip().strip("`") for f in re.split(r"[,\s;]+", m.group(1)) if "/" in f or "." in f}
        return sorted(f for f in files if f and not TBD_RE.search(f))

    def _allowed_files(self, plan_path: str, files_path: str) -> tuple[list[str], str]:
        """The files the code step may touch: files.txt from the files step when wired, else the plan's task blocks."""
        if files_path and Path(files_path).is_file():
            return read_files_txt(Path(files_path)), "files.txt"
        return self._plan_files(plan_path), "plan.md"

    def _record_diff(self, patch: Path, sdir: Path, rec: dict, plan_path: str, summary: str, files_path: str = "") -> None:
        text = patch.read_text(encoding="utf-8", errors="replace")
        changed = sorted({m.group(1) for m in re.finditer(r"^\+\+\+ b/(\S+)", text, re.M)}
                         | {m.group(1) for m in re.finditer(r"^--- a/(\S+)", text, re.M)})
        plan_files, source = self._allowed_files(plan_path, files_path)
        outside = [f for f in changed if plan_files and f not in plan_files and not TEST_PATH_RE.search(f)]
        shutil.copy(patch, sdir / "diff.patch")
        write_json(sdir / "files-changed.json", {"files": changed, "plan_files": plan_files, "plan_files_source": source, "outside_plan": outside,
                                                 "lines_added": sum(1 for ln in text.splitlines() if ln.startswith("+") and not ln.startswith("+++")),
                                                 "lines_removed": sum(1 for ln in text.splitlines() if ln.startswith("-") and not ln.startswith("---"))})
        md = [f"# Builder summary — {self.args.builder}", "", summary.strip() or "(no summary)", "",
              "## Files changed", ""] + [f"- `{f}`" + (f" — NOT named in {source}" if f in outside else "") for f in changed] + [""]
        (sdir / "agent-summary.md").write_text("\n".join(md), encoding="utf-8")
        rec.update(exit=0, files_changed=len(changed), outside_plan=outside)

    # ---- the files step (agent step with produces: ["files.txt"])
    def _derive_files_txt(self, tasks_path: str) -> tuple[list[str], str]:
        """files.txt from tasks.csv when EVERY task names files (nothing invented); else ([], why-not)."""
        if not tasks_path or not Path(tasks_path).is_file():
            return [], "no tasks.csv to derive from"
        rows = list(csv.DictReader(io.StringIO(Path(tasks_path).read_text(encoding="utf-8"))))
        if not rows:
            return [], "tasks.csv has no tasks"
        files: list[str] = []
        for r in rows:
            cell = (r.get("files") or "").strip()
            if not cell or TBD_RE.search(cell):
                return [], f"task {r.get('id') or '?'} names no files in tasks.csv"
            for f in re.split(r"[,;]+", cell):
                f = repo_path(f)
                if f and f not in files:
                    files.append(f)
        return files, ""

    def step_files(self, step: dict, sdir: Path, rec: dict) -> bool:
        builder = self.args.builder
        rec["builder"] = builder
        plan = str(self.resolve(step["inputs"].get("plan"), "files plan"))
        tasks = str(self.resolve(step["inputs"].get("tasks", ""), "files tasks") or "")
        target = Path(str(self.resolve(step["inputs"].get("target", "$repo"), "files target")))
        expected = sdir / FILES_TXT
        dropped = self.out / "build" / FILES_TXT          # where --files copies to; an alternative drop point

        def record(files: list[str], source: str, note: str) -> bool:
            if not files:
                raise StepError(f"{source} names no files: the build has nothing to constrain")
            missing = [f for f in files if not (target / f).exists()]
            write_json(sdir / "files.json", {"files": files, "source": source, "derived": source == "tasks.csv",
                                             "create": missing, "modify": [f for f in files if f not in missing], "note": note})
            rec.update(exit=0, files=len(files), files_source=source)
            return True

        derived, why = self._derive_files_txt(tasks)
        if derived and not expected.is_file() and not dropped.is_file():
            expected.write_text(f"# derived by deliver.py from tasks.csv: every task names its files (checked against {target.name})\n"
                                + "".join(f"{f}\n" for f in derived), encoding="utf-8")
            return record(derived, "tasks.csv", "derived — the builder was not asked")
        if not expected.is_file() and dropped.is_file():
            shutil.copy(dropped, expected)
        if expected.is_file():
            head = expected.read_text(encoding="utf-8", errors="replace").lstrip().split("\n", 1)[0]
            source = "tasks.csv" if head.startswith("# derived by deliver.py") else ("claude-code" if builder == "claude-code" else "builder")
            return record(read_files_txt(expected), source, f"supplied at {expected.relative_to(self.out)} (builder: {builder})")
        if builder in ("none", "manual"):
            rec["status"] = "awaiting_builder"
            write_json(self.out / "needs_builder.json", {
                "run_id": self.run_id, "pipeline": self.spec["name"], "stage": rec["stage"], "step": step["id"],
                "builder": builder, "target": str(target), "plan": plan, "tasks": tasks or None,
                "why": f"files.txt could not be derived: {why}",
                "produce": FILES_TXT, "expected": str(expected), "alternative": str(dropped),
                "format": "one repo-relative path per line (source files the change will create or modify; test files are not "
                          "needed — the tests step adds them); blank lines and `#` comments are ignored",
                "rule": "read plan.md / tasks.csv and the checkout; list only files the plan's tasks require; nothing invented",
                "how": f"write {FILES_TXT} at the expected path (or pass --files <file>), then re-run with --resume"})
            return False
        if builder == "claude-code":
            exe = shutil.which("claude")
            if not exe:
                raise StepError("builder claude-code: `claude` is not on PATH (install Claude Code, or use --builder manual with files.txt)")
            prompt = self.files_prompt(step, plan, tasks, expected)
            (sdir / "prompt.txt").write_text(prompt, encoding="utf-8")
            t0 = time.time()
            r = subprocess.run([exe, "-p", prompt, "--output-format", "text"], cwd=str(target), capture_output=True,
                               text=True, timeout=1800)
            rec["agent_exit"], rec["agent_duration_s"] = r.returncode, round(time.time() - t0, 3)
            (sdir / "agent-stderr.txt").write_text(r.stderr, encoding="utf-8")
            (sdir / "agent-stdout.txt").write_text(r.stdout, encoding="utf-8")
            if r.returncode != 0:
                raise StepError(f"claude -p exited {r.returncode}: {r.stderr.strip().splitlines()[-1:] or ''}"[:300])
            if not expected.is_file():
                raise StepError(f"builder claude-code did not write {expected}")
            if is_git_root(target) and shutil.which("git"):
                _, dirty = git(target, "status", "--porcelain")
                if dirty.strip():
                    rec["warning"] = "the files step changed the checkout; it should only read it"
            return record(read_files_txt(expected), "claude-code", f"written by claude -p at {expected.relative_to(self.out)}")
        raise StepError(f"unknown builder {builder!r}")

    def files_prompt(self, step: dict, plan: str, tasks: str, expected: Path) -> str:
        def body(p: str) -> str:
            t = Path(p).read_text(encoding="utf-8", errors="replace") if p and Path(p).is_file() else "(missing)"
            return t if len(t) <= CONTEXT_LIMIT else t[:CONTEXT_LIMIT] + "\n[... truncated ...]"
        parts = ["You are the files step of a delivery pipeline. Read the plan below and this repository, then write the list of "
                 "repo-relative source files the change will create or modify — one path per line, nothing else — to:",
                 str(expected), "",
                 "Rules: list only files the plan's tasks require (existing files to modify, new files to create); do not list "
                 "test files (the tests step adds them); do not change any file in the repository; do not commit.",
                 "", "## Plan", "", body(plan)]
        if tasks:
            parts += ["", "## tasks.csv", "", body(tasks)]
        parts += ["", "## Stack profile", "", json.dumps(self.record.get("stack_profile", {}), indent=2),
                  "", "When done, reply with the list you wrote."]
        return "\n".join(parts)

    # ---- the plan-refine step (agent step with produces: ["plan.md", "tasks.csv"])
    @staticmethod
    def scaffold_gaps(tasks_path: str) -> list[str]:
        """What keeps the spec-to-plan scaffold from being a plan: one line per task field that is empty or TBD
        (acceptance, test, files). Empty list = complete, the architect has nothing to add."""
        if not tasks_path or not Path(tasks_path).is_file():
            return ["no tasks.csv"]
        rows = list(csv.DictReader(io.StringIO(Path(tasks_path).read_text(encoding="utf-8"))))
        if not rows:
            return ["tasks.csv has no tasks"]
        gaps = []
        for r in rows:
            for col in PLAN_FILLED:
                v = (r.get(col) or "").strip()
                if not v:
                    gaps.append(f"{r.get('id') or '?'}: {col} is empty")
                elif TBD_RE.search(v):
                    gaps.append(f"{r.get('id') or '?'}: {col} is {v}")
        return gaps

    def step_plan_refine(self, step: dict, sdir: Path, rec: dict) -> bool:
        builder = self.args.builder
        rec["builder"] = builder
        scaffold_plan = str(self.resolve(step["inputs"].get("plan"), "plan-refine plan"))
        scaffold_tasks = str(self.resolve(step["inputs"].get("tasks", ""), "plan-refine tasks") or "")
        prd = str(self.resolve(step["inputs"].get("prd", ""), "plan-refine prd") or "")
        request = str(self.resolve(step["inputs"].get("request", ""), "plan-refine request") or self.inputs.get("request", ""))
        target = Path(str(self.resolve(step["inputs"].get("target", "$repo"), "plan-refine target")))
        expected = {f: sdir / f for f in PLAN_FILES}
        dropped = {f: self.out / "build" / "plan" / f for f in PLAN_FILES}   # where --plan DIR copies to

        def record(source: str, note: str, skipped: bool = False) -> bool:
            rows = list(csv.DictReader(io.StringIO(expected[TASKS_CSV].read_text(encoding="utf-8"))))
            header = list(rows[0].keys()) if rows else next(csv.reader(io.StringIO(expected[TASKS_CSV].read_text(encoding="utf-8"))), [])
            missing_cols = [c for c in PLAN_COLUMNS if c not in header]
            if missing_cols:
                raise StepError(f"{TASKS_CSV} from {source} lacks the columns {missing_cols} (spec-to-plan's header: {','.join(PLAN_COLUMNS)})")
            gaps = self.scaffold_gaps(str(expected[TASKS_CSV]))
            write_json(sdir / "plan-refine.json", {"source": source, "skipped": skipped, "tasks": len(rows), "gaps": gaps,
                                                   "scaffold": {"plan": scaffold_plan, "tasks": scaffold_tasks}, "note": note})
            rec.update(exit=0, plan_source=source, skipped=skipped, tasks=len(rows), gaps=len(gaps))
            return True

        if not all(p.is_file() for p in expected.values()) and all(p.is_file() for p in dropped.values()):
            for f in PLAN_FILES:
                shutil.copy(dropped[f], expected[f])
        if all(p.is_file() for p in expected.values()):
            source = "claude-code" if builder == "claude-code" and (sdir / "prompt.txt").is_file() else "architect"
            return record(source, f"refined plan supplied at {sdir.relative_to(self.out)} (builder: {builder})")
        gaps = self.scaffold_gaps(scaffold_tasks)
        if not gaps:   # the scaffold is already a plan: take it as is, deterministically — nobody is asked
            shutil.copy(scaffold_plan, expected[PLAN_MD])
            shutil.copy(scaffold_tasks, expected[TASKS_CSV])
            return record("scaffold", "the spec-to-plan scaffold is complete (every task names files, acceptance and test): "
                          "step skipped, scaffold taken as the plan", skipped=True)
        if builder in ("none", "manual"):
            rec["status"] = "awaiting_builder"
            write_json(self.out / "needs_builder.json", {
                "run_id": self.run_id, "pipeline": self.spec["name"], "stage": rec["stage"], "step": step["id"],
                "role": "architect", "builder": builder, "target": str(target),
                "plan": scaffold_plan, "tasks": scaffold_tasks, "prd": prd or None, "request": request,
                "why": "the scaffold plan is not a plan yet: " + "; ".join(gaps[:8]) + (" …" if len(gaps) > 8 else ""),
                "produce": list(PLAN_FILES),
                "expected": {f: str(expected[f]) for f in PLAN_FILES},
                "alternative": {f: str(dropped[f]) for f in PLAN_FILES},
                "format": f"{TASKS_CSV}: columns {','.join(PLAN_COLUMNS)}; files repo-relative, comma-separated; repo_check "
                          f"`<file>: create|modify` per the checkout; {PLAN_MD}: the scaffold with its file table and every task "
                          "block filled (Files, Acceptance, Tests, Rollback)",
                "rule": "read the scaffold plan, the PRD and the checkout; fill the file table and every task's acceptance, test, "
                        "rollback and files; nothing invented beyond what the PRD and the request state; the gate refuses any "
                        "[TO BE BASELINED cell in acceptance, test or files",
                "how": f"write both files at the expected paths (or pass --plan <dir> holding {PLAN_MD} and {TASKS_CSV}), then re-run with --resume"})
            return False
        if builder == "claude-code":
            exe = shutil.which("claude")
            if not exe:
                raise StepError("builder claude-code: `claude` is not on PATH (install Claude Code, or use --builder manual with --plan <dir>)")
            prompt = self.plan_prompt(scaffold_plan, scaffold_tasks, prd, request, expected, gaps)
            (sdir / "prompt.txt").write_text(prompt, encoding="utf-8")
            t0 = time.time()
            r = subprocess.run([exe, "-p", prompt, "--output-format", "text"], cwd=str(target), capture_output=True,
                               text=True, timeout=1800)
            rec["agent_exit"], rec["agent_duration_s"] = r.returncode, round(time.time() - t0, 3)
            (sdir / "agent-stderr.txt").write_text(r.stderr, encoding="utf-8")
            (sdir / "agent-stdout.txt").write_text(r.stdout, encoding="utf-8")
            if r.returncode != 0:
                raise StepError(f"claude -p exited {r.returncode}: {r.stderr.strip().splitlines()[-1:] or ''}"[:300])
            absent = [f for f in PLAN_FILES if not expected[f].is_file()]
            if absent:
                raise StepError(f"builder claude-code did not write {', '.join(str(expected[f]) for f in absent)}")
            if is_git_root(target) and shutil.which("git"):
                _, dirty = git(target, "status", "--porcelain")
                if dirty.strip():
                    rec["warning"] = "the plan-refine step changed the checkout; it should only read it"
            return record("claude-code", f"written by claude -p at {sdir.relative_to(self.out)}")
        raise StepError(f"unknown builder {builder!r}")

    def plan_prompt(self, plan: str, tasks: str, prd: str, request: str, expected: dict, gaps: list[str]) -> str:
        def body(p: str) -> str:
            t = Path(p).read_text(encoding="utf-8", errors="replace") if p and Path(p).is_file() else "(missing)"
            return t if len(t) <= CONTEXT_LIMIT else t[:CONTEXT_LIMIT] + "\n[... truncated ...]"
        parts = ["You are the architect of a delivery pipeline. The plan below is a scaffold spec-to-plan wrote from the spec; "
                 "it is not a plan yet. Read it, the PRD, the request and this repository, then write the complete plan to:",
                 f"  {expected[PLAN_MD]}", f"  {expected[TASKS_CSV]}", "",
                 "Rules: keep the scaffold's structure and task ids; fill the file table and, for every task, Files (repo-relative "
                 "source files to create or modify, checked against this checkout and marked create/modify under Repo check), "
                 "Acceptance (observable), Tests (what the red test asserts) and Rollback; nothing invented beyond what the PRD "
                 f"and the request state — where they are silent, say so in the task text rather than guessing. {TASKS_CSV} keeps "
                 f"the columns {','.join(PLAN_COLUMNS)}; files comma-separated; repo_check `<file>: create|modify`. Leave no "
                 "[TO BE BASELINED cell in acceptance, test or files: the stage gate refuses them. Do not change any file in the "
                 "repository; do not commit.",
                 "", "## Gaps the gate will refuse", ""] + [f"- {g}" for g in gaps] + [
                 "", "## Request", "", request or "(none)", "", "## PRD", "", body(prd), "", "## Scaffold plan.md", "", body(plan),
                 "", f"## Scaffold {TASKS_CSV}", "", body(tasks),
                 "", "## Stack profile", "", json.dumps(self.record.get("stack_profile", {}), indent=2),
                 "", "When done, reply with the task table you wrote."]
        return "\n".join(parts)

    def _revert_superseded_patch(self, patch: Path, target: Path, sdir: Path, rec: dict) -> None:
        """The code step runs again (a resume after a failed gate, or build/diff.patch changed after the build stage
        passed) and the checkout still carries the EARLIER diff — the one this step's evidence recorded. Take it back
        out with `git apply --reverse` so the new diff lands on the pre-change tree; nothing else on the checkout is
        touched. A checkout that no longer carries the earlier diff (the developer reset it) is left alone: the apply
        that follows reports on its own terms. Evidence: rec['superseded_patch']."""
        prior = sdir / "diff.patch"
        if not prior.is_file() or not shutil.which("git") or not is_git_root(target):
            return
        old_sha, new_sha = sha256_file(prior), sha256_file(patch)
        if old_sha == new_sha:
            return
        body = "\n".join(ln for ln in prior.read_text(encoding="utf-8", errors="replace").splitlines() if not ln.startswith("# ")) + "\n"
        clean = self.out / "build" / ".deliver-revert.patch"
        clean.write_text(body, encoding="utf-8")
        note = {"previous_sha256": old_sha, "sha256": new_sha, "reverted": False}
        try:
            def apply(*flags: str) -> subprocess.CompletedProcess:
                return subprocess.run(["git", "-c", "commit.gpgsign=false", "apply", "--reverse", *flags, str(clean)], cwd=str(target),
                                      capture_output=True, text=True, env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
            check = apply("--check")
            if check.returncode == 0:
                r = apply() if self.args.dry else apply("--index")
                note["reverted"] = r.returncode == 0
                if r.returncode != 0:
                    note["error"] = (r.stderr or r.stdout).strip()[:300]
            else:
                note["error"] = "the checkout no longer carries the earlier diff: " + (check.stderr or check.stdout).strip()[:300]
        finally:
            clean.unlink(missing_ok=True)
        rec["superseded_patch"] = note

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

    @staticmethod
    def _patch_files(text: str) -> list[str]:
        """The repo-relative paths a unified diff touches (creates, modifies, deletes, renames)."""
        return sorted({m.group(1) for m in re.finditer(r"^\+\+\+ b/(\S+)", text, re.M)}
                      | {m.group(1) for m in re.finditer(r"^--- a/(\S+)", text, re.M)})

    def _apply_manual(self, patch: Path, target: Path, allowed: list[str], source: str, sdir: Path, rec: dict) -> str:
        """--builder manual|none outside --dry: land build/diff.patch on the checkout with `git apply --index`, so the
        conventions / perf / ui gates and the pr step see the change. Refuses (StepError → exit 1, named in the gate
        detail) when the diff touches a file outside files.txt + test paths or does not apply cleanly. Idempotent: a
        diff the checkout already carries (`git apply --check --reverse` succeeds — the IDE agent wrote the code
        itself, or this is a resume) is skipped. Evidence: <step>/applied.json (files, git diff --stat)."""
        if not shutil.which("git") or not is_git_root(target):
            raise StepError(f"builder {self.args.builder}: {target} is not a git repository root; build/diff.patch cannot be applied "
                            "(check the repo out with git, or run with --dry)")
        text = patch.read_text(encoding="utf-8", errors="replace")
        touched = self._patch_files(text)
        if not touched:
            raise StepError("build/diff.patch has no `diff --git` / `+++ b/` headers: not a git diff (save `git diff` with new files added)")
        outside = [f for f in touched if allowed and f not in allowed and not TEST_PATH_RE.search(f)]
        if outside:
            raise StepError(f"build/diff.patch touches {len(outside)} file(s) outside {source} + test paths: " + ", ".join(outside)
                            + f" — the code step may change only {', '.join(allowed)} (plus tests); fix the diff or files.txt")
        body = "\n".join(ln for ln in text.splitlines() if not ln.startswith("# ")) + "\n"
        clean = self.out / "build" / ".deliver-apply.patch"
        clean.write_text(body, encoding="utf-8")
        applied = {"patch": "build/diff.patch", "files": touched, "allowed_source": source}
        try:
            def apply(*flags: str) -> subprocess.CompletedProcess:
                return subprocess.run(["git", "-c", "commit.gpgsign=false", "apply", *flags, str(clean)], cwd=str(target),
                                      capture_output=True, text=True, env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
            if apply("--check", "--reverse").returncode == 0:
                applied["status"] = "already-applied"
                note = "already on the checkout (git apply --check --reverse succeeded): not applied again."
            else:
                check = apply("--check")
                if check.returncode != 0:
                    why = (check.stderr or check.stdout).strip().splitlines()
                    raise StepError("build/diff.patch does not apply cleanly to the checkout (git apply --check): "
                                    + "; ".join(why[:4])[:300] + " — regenerate the diff against the current checkout, then --resume")
                r = apply("--index")
                if r.returncode != 0:
                    raise StepError(f"git apply --index failed: {(r.stderr or r.stdout).strip()[:300]}")
                applied["status"] = "applied"
                note = "applied to the checkout with `git apply --index` so the gates and the pr step see the change."
        finally:
            clean.unlink(missing_ok=True)
        _, stat = git(target, "diff", "--stat", "HEAD", "--", *touched, ok=(0, 128))
        applied["diff_stat"] = stat.strip()
        write_json(sdir / "applied.json", applied)
        rec.update(applied=applied["status"], applied_files=touched, diff_stat=applied["diff_stat"])
        return note

    def step_agent(self, step: dict, sdir: Path, rec: dict) -> bool:
        produces = step.get("produces") or []
        if FILES_TXT in produces:
            return self.step_files(step, sdir, rec)
        if TASKS_CSV in produces:
            return self.step_plan_refine(step, sdir, rec)
        builder = self.args.builder
        rec["builder"] = builder
        plan = str(self.resolve(step["inputs"].get("plan"), "agent plan"))
        tests = str(self.resolve(step["inputs"].get("tests", ""), "agent tests") or "")
        files = str(self.resolve(step["inputs"].get("files", ""), "agent files") or "")
        target = Path(str(self.resolve(step["inputs"].get("target", "$repo"), "agent target")))
        allowed, allowed_source = self._allowed_files(plan, files)
        rec["allowed_files"] = allowed
        manual_patch = self.out / "build" / "diff.patch"
        if builder in ("none", "manual"):
            if manual_patch.is_file():
                rec["patch_sha256"] = sha256_file(manual_patch)
                self._revert_superseded_patch(manual_patch, target, sdir, rec)
                if self.args.dry:  # the checkout is a throwaway copy: land the diff so the lint stages assess the change
                    note = self._apply_to_copy(manual_patch, target)
                else:              # the real checkout: the diff is what the gates and the PR must see
                    note = self._apply_manual(manual_patch, target, allowed, allowed_source, sdir, rec)
                self._record_diff(manual_patch, sdir, rec, plan, f"Diff supplied at build/diff.patch (builder: {builder}); {note}", files)
                return True
            rec["status"] = "awaiting_builder"
            write_json(self.out / "needs_builder.json", {
                "run_id": self.run_id, "pipeline": self.spec["name"], "stage": rec["stage"], "step": step["id"],
                "builder": builder, "target": str(target), "plan": plan, "tests": tests, "files": files or None,
                "allowed_files": allowed, "allowed_files_source": allowed_source,
                "constraints": [str(ROOT / c) for c in step.get("constraints") or []],
                "rule": f"touch only the files {allowed_source} names (plus the test files the test plan names); make the red tests green; no other changes",
                "produce": "diff.patch", "expected": str(manual_patch),
                "how": "write the code on the checkout, save `git diff` (staged + unstaged, new files included) to the "
                       "expected path (or pass --patch <file>), then re-run with --resume"})
            return False
        if builder == "claude-code":
            exe = shutil.which("claude")
            if not exe:
                raise StepError("builder claude-code: `claude` is not on PATH (install Claude Code, or use --builder manual with build/diff.patch)")
            if not is_git_root(target):
                raise StepError(f"builder claude-code: {target} is not a git repository root; the diff cannot be captured")
            prompt = self.agent_prompt(step, plan, tests, allowed, allowed_source)
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
            self._record_diff(patch, sdir, rec, plan, r.stdout, files)
            patch.unlink()
            return True
        raise StepError(f"unknown builder {builder!r}")

    def agent_prompt(self, step: dict, plan: str, tests: str, allowed: list[str] | None = None, source: str = "plan.md") -> str:
        def body(p: str) -> str:
            t = Path(p).read_text(encoding="utf-8", errors="replace") if p and Path(p).is_file() else "(missing)"
            return t if len(t) <= CONTEXT_LIMIT else t[:CONTEXT_LIMIT] + "\n[... truncated ...]"
        parts = ["You are the build step of a delivery pipeline. Implement the plan below on this repository.",
                 f"Rules: touch ONLY the files listed under 'Files you may touch' (from {source}) plus the test files the test "
                 "plan names; make the red tests green; follow every constraint file; do not refactor, rename or reformat "
                 "anything else; do not commit.",
                 "", "## Files you may touch", ""] + [f"- {f}" for f in (allowed or [])] + (["(none listed: the plan names the files)"] if not allowed else []) + [
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
        env = {**os.environ, **BOT_GIT_ENV}
        if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
            # CI: let git push with the token gh holds (credential helper), so the push below needs no remote rewrite
            subprocess.run(["gh", "auth", "setup-git"], cwd=str(repo), capture_output=True, text=True)
        code, _ = git(repo, "rev-parse", "--verify", "-q", branch, ok=(0, 1), env=env)
        git(repo, "checkout", "-q", "-B" if code == 0 else "-b", branch, env=env)
        git(repo, "add", "-A", env=env)
        staged, _ = git(repo, "diff", "--cached", "--quiet", ok=(0, 1), env=env)
        _, head = git(repo, "rev-parse", "HEAD", env=env)
        # a resume after a failed push: the delivery commit is already on the branch — nothing staged and HEAD is not
        # the base commit — so it is pushed as it is instead of stacking an empty commit on it
        if staged == 1 or head.strip() == (self.record.get("base_sha") or ""):
            git(repo, "commit", "-q", "--allow-empty", "-m", title, "-m",
                f"Delivered by giri-skills pipeline {self.spec['name']} run {self.run_id}", env=env)
            _, head = git(repo, "rev-parse", "HEAD", env=env)
        push = subprocess.run(["git", "push", "-u", "origin", branch], cwd=str(repo), capture_output=True, text=True, env=env)
        if push.returncode != 0:
            why = push.stderr or push.stdout
            hint = (f" — the token gh uses cannot push to this repository: grant Contents: read and write + Pull requests: "
                    f"read and write, then --resume (the commit is on branch {branch} already)") if "403" in why or "not granted" in why else ""
            raise StepError(f"git push -u origin {branch}: {why.strip()[:300]}{hint}")
        existing = subprocess.run(["gh", "pr", "view", branch, "--json", "number,url,headRefOid"], cwd=str(repo),
                                  capture_output=True, text=True, env=env)
        r = existing if existing.returncode == 0 and existing.stdout.strip().startswith("{") else \
            subprocess.run(["gh", "pr", "create", "--title", title, "--body-file", body, "--head", branch],
                           cwd=str(repo), capture_output=True, text=True, env=env)
        if r.returncode != 0:
            raise StepError(f"gh pr create: {(r.stderr or r.stdout).strip()[:300]}")
        v = subprocess.run(["gh", "pr", "view", branch, "--json", "number,url,headRefOid"], cwd=str(repo),
                           capture_output=True, text=True, env=env)
        info = {}
        if v.returncode == 0 and v.stdout.strip():
            try:
                info = json.loads(v.stdout)
            except ValueError:
                info = {}
        url = info.get("url") or next((ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith("http")), None)
        write_json(sdir / "pr.json", {"dry": False, "branch": branch, "title": title, "number": info.get("number"),
                                      "url": url, "head_sha": info.get("headRefOid") or head.strip(),
                                      "committed_as": BOT_NAME})
        rec["exit"] = 0

    # ---- gates
    def pre_approval_gate(self, gate: dict, stage_rec: dict) -> tuple[str, str]:
        """The stage gate with its approval parts left out: what must already hold before a person is asked to
        approve. A failing output check here fails the stage without writing needs_approval.json."""
        kind = gate.get("kind")
        if kind == "approval":
            return "pass", "approval pending"
        if kind in ("all", "any"):
            parts = [g for g in gate.get("of") or [] if g.get("kind") != "approval"]
            if not parts:
                return "pass", "approval pending"
            return self.eval_gate({"kind": kind, "of": parts}, stage_rec)
        return self.eval_gate(gate, stage_rec)

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
                self.baseline_row(), "",
                "| Stage | Role | Gate | Verdict | Evidence |", "|---|---|---|---|---|"]
        for s in self.record.get("stages", []):
            g = s.get("gate") or {}
            ev = ", ".join(f"[{Path(p).name}]({p})" for p in s.get("evidence_files") or []) or "—"
            verdict = {"pass": "PASS", "fail": "FAIL", "recorded": "RECORDED"}.get(g.get("verdict", ""), s.get("status", "").upper())
            rows.append(f"| {s['id']} | {s['role']} | {g.get('kind', '')} | {verdict} | {ev} |")
        rows += ["", "Gate detail per stage is in `<stage>/gate.json`; step logs in `<stage>/<step>/`.", ""]
        (self.evidence / "EVIDENCE.md").write_text("\n".join(rows), encoding="utf-8")

    def baseline_row(self) -> str:
        """The Baseline line of EVIDENCE.md: findings per check before the change (the gates fail only on new high ones)."""
        b = self.record.get("baseline") or self.baseline
        if not b:
            return "Baseline (before the change): not captured yet — taken before the build stage's code step."
        if b.get("status") != "captured":
            return f"Baseline (before the change): {b.get('status', '')} — {b.get('reason', '')}"
        cells = []
        for check, e in sorted((b.get("checks") or {}).items()):
            if e.get("source") == "error":
                cells.append(f"{check}: not available ({e.get('error', '')})")
                continue
            link = f"[findings.csv]({e['path']})" if e.get("source") == "captured" else "repo-recorded (docs/baselines)"
            cells.append(f"{check}: {e.get('findings', 0)} finding(s), {e.get('high', 0)} high — {link}")
        return "Baseline (before the change, " + b.get("target_source", "") + "): " + ("; ".join(cells) or "no checks") + \
            ". Gates fail only on findings that are new against it."

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

    # ---- portal callback
    def stage_evidence(self, srec: dict) -> list[dict]:
        """{path, sha256, bytes} for the stage's evidence files and its gate.json (paths relative to evidence/)."""
        items = []
        rels = list(srec.get("evidence_files") or [])
        gate = Path(srec.get("dir", "")) / "gate.json" if srec.get("dir") else None
        if gate and (self.out / gate).is_file():
            rels.append(str((self.out / gate).relative_to(self.evidence)))
        for rel in rels[:200]:
            p = self.evidence / rel
            if p.is_file():
                items.append({"path": rel, "sha256": sha256(p), "bytes": p.stat().st_size})
        return items

    def post_stage(self, record: dict, started_at: str | None = None, finished_at: str | None = None, pr: dict | None = None) -> None:
        """One DeliveryStageInput to the portal (no-op without --run/--portal). The first post carries the stack
        profile; every post carries the executor ref when GitHub Actions provides one."""
        if not self.portal:
            return
        body = dict(record)
        if started_at:
            body["started_at"] = to_utc(started_at)
        if finished_at:
            body["finished_at"] = to_utc(finished_at)
        if not self.profile_posted and self.profile:
            body["stack_profile"] = self.record.get("stack_profile") or {}
            self.profile_posted = True
        if pr:
            body["pr"] = pr
        ref = executor_ref()
        if ref:
            body["executor_ref"] = ref
        self.portal.post_stage(body)

    def post_profile(self, stage_id: str) -> None:
        """After the stack profile: the next stage is running, and the profile travels with that post."""
        self.post_stage({"id": stage_id, "status": "running"}, started_at=now())

    def post_stage_result(self, srec: dict) -> None:
        """After a stage: its outcome, gate verdict, evidence hashes and (for the stage that opened it) the PR."""
        status = STAGE_STATUS.get(srec.get("status", ""), "running")
        g = srec.get("gate") or {}
        verdict = {"pass": "pass", "recorded": "pass", "fail": "fail", "pending": "pending"}.get(g.get("verdict", ""), "pending")
        body = {"id": srec["id"], "adlc_stage": srec.get("adlc_stage") or srec["id"], "role": srec.get("role") or "",
                "status": status, "gate": {"kind": str(g.get("kind", "")), "verdict": verdict, "detail": str(g.get("detail", ""))[:4000]},
                "evidence": self.stage_evidence(srec)}
        failed = next((st for st in srec.get("steps", []) if st.get("status") == "failed"), None)
        if srec.get("status") in ("failed", "wiring_error") and failed:
            body["error"] = f"{failed['id']}: {failed.get('error', '')}"[:4000]
        pr = None
        for st in srec.get("steps", []):
            if st.get("kind") == "pr" and st.get("status") == "ok":
                pj = self.step_dirs.get(st["id"], Path("/nonexistent")) / "pr.json"
                if pj.is_file():
                    info = read_json(pj)
                    if not info.get("dry") and info.get("url"):
                        pr = {k: v for k, v in (("number", info.get("number")), ("url", info.get("url")), ("head_sha", info.get("head_sha"))) if v}
        self.post_stage(body, started_at=srec.get("started_at"), finished_at=now() if status != "awaiting_approval" else None, pr=pr)

    # ---- stages
    def run_stage(self, n: int, stage: dict, prev: dict | None, approvals: dict) -> tuple[str, int]:
        stage_dir = self.evidence / f"{n:02d}-{stage['id']}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        srec = {"id": stage["id"], "adlc_stage": stage.get("adlc_stage"), "role": stage.get("role"), "dir": str(stage_dir.relative_to(self.out)),
                "status": "running", "started_at": now(), "steps": []}
        # Steps are kept across a resume only when the stage STOPPED (waiting for an approval or a builder): the work
        # before the stop stands. A stage whose gate FAILED runs every step again — the gate must judge fresh outputs
        # (found by the first real run: the fixed reviewer and security skills were never re-run; the resume re-judged
        # the stale review.md/findings.csv and failed again).
        keep = (prev or {}).get("status") in ("awaiting_approval", "awaiting_builder")
        done_steps = {s["id"]: s for s in (prev or {}).get("steps", []) if keep and s.get("status") in ("ok", "approved") and not s.get("exit")}
        self.stage_started = srec["started_at"]
        t_stage = time.time()
        halted = ""
        try:   # a resume at or past the code step with no baseline yet: take it before any gate skill runs
            self.ensure_baseline(n - 1)
        except StepError as e:
            halted = f"baseline: {e}"
            srec["steps"].append({"id": "baseline", "kind": "baseline", "stage": stage["id"], "status": "failed", "error": str(e)[:400]})
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
                    # what the gate checks on the stage's outputs must hold BEFORE anyone is asked: a plan the gate
                    # would refuse (TBD cells, no files) is never put in front of an approver
                    pre_verdict, pre_detail = self.pre_approval_gate(stage["gate"], {"steps": srec["steps"]})
                    if pre_verdict == "fail":
                        raise StepError(f"not submitted for approval — the stage gate refuses the outputs: {pre_detail}")
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
                    if not (step.get("produces") or []):   # the code step: baseline the untouched code first
                        self.capture_baseline(n - 1, step)
                        rec["baseline"] = self.baseline.get("status", "")
                    if not self.step_agent(step, sdir, rec):
                        rec["duration_s"] = round(time.time() - t0, 3)
                        srec["steps"].append(rec)
                        srec.update(status="awaiting_builder", duration_s=round(time.time() - t_stage, 3))
                        who = "architect (the refined plan.md / tasks.csv)" if TASKS_CSV in (step.get("produces") or []) else "builder"
                        srec["gate"] = {"verdict": "pending", "kind": stage["gate"]["kind"], "detail": f"waiting for the {who} at step '{sid}'",
                                        "role": stage.get("role"), "approved_by": "", "at": now()}
                        write_json(stage_dir / "gate.json", srec["gate"])
                        self._finish_stage(srec, stage)
                        return "awaiting_builder", EXIT_BUILDER
                elif step["kind"] == "pr":
                    self.step_pr(step, sdir, rec)
                else:
                    raise StepError(f"unknown step kind {step.get('kind')!r}")
            except WiringError as e:
                # the pipeline, not the work, is wrong: never a gate verdict — stop with exit 2 and say which wire is missing
                rec.update(status="failed", error=str(e)[:400], duration_s=round(time.time() - t0, 3))
                srec["steps"].append(rec)
                srec.update(status="wiring_error", duration_s=round(time.time() - t_stage, 3))
                srec["gate"] = {"verdict": "fail", "kind": stage["gate"]["kind"], "detail": str(e)[:400],
                                "role": stage.get("role"), "approved_by": "", "at": now()}
                write_json(stage_dir / "gate.json", srec["gate"])
                write_json(self.out / "wiring_error.json", {
                    "run_id": self.run_id, "pipeline": self.spec["name"], "stage": stage["id"], "step": e.step,
                    "input": e.input, "skill": e.skill, "reference": (step.get("inputs") or {}).get(e.input),
                    "message": str(e),
                    "how": "fix the pipeline file (wire the input from a step that produces it, or add the step that does), "
                           "then start a new run; this is not a gate failure and not a missing user input"})
                self._finish_stage(srec, stage)
                return "wiring_error", EXIT_ARGS
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

def load_pipeline(arg: str, portal: "Portal | None" = None, out: Path | None = None) -> tuple[dict, Path]:
    """A path, a name under pipelines/ or pipelines/composed/, or — in portal mode — the composed pipeline the
    portal stored on the run (`pipeline_spec`, docs/DELIVERY-PIPELINES.md → When no template fits), saved to
    <out>/pipeline.json so --resume finds it again."""
    p = Path(arg)
    if not p.is_file():
        p = ROOT / "pipelines" / f"{arg}.json"
    if not p.is_file():
        p = ROOT / "pipelines" / "composed" / f"{arg}.json"
    if not p.is_file() and out is not None and (out / "pipeline.json").is_file():
        p = out / "pipeline.json"
    if not p.is_file() and portal is not None:
        run = portal.get_run()
        spec = (run or {}).get("pipeline_spec")
        if isinstance(spec, dict) and spec.get("name") == arg:
            out.mkdir(parents=True, exist_ok=True)
            p = out / "pipeline.json"
            write_json(p, spec)
            return spec, Path(f"{arg}.json")
    if not p.is_file():
        sys.exit(f"error: pipeline not found: {arg} (a name under pipelines/ or pipelines/composed/, a path, or a composed "
                 "pipeline stored on the portal run)")
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
        elif REPO_KEY.match(str(run.inputs["repo"])):
            # the portal names repositories owner/name: clone it under the run (the token in GH_TOKEN, via gh)
            src = clone_repo(str(run.inputs["repo"]), run.out / "repo", str(run.inputs.get("ref") or ""))
        else:
            sys.exit(f"error: --repo {src} is not a directory (give a local checkout, or owner/name to clone it)")
    run.repo = src.resolve()
    if run.inputs.get("ref") and is_git_root(run.repo):
        git(run.repo, "checkout", "-q", str(run.inputs["ref"]))
    check_push_access(run)


def github_key(run: "Run") -> str:
    """owner/name of the repository the pr step will push to: the --repo key, or the origin remote of the checkout."""
    key = str(run.inputs.get("repo") or "")
    if REPO_KEY.match(key):
        return key
    if shutil.which("git") and is_git_root(run.repo):
        code, url = git(run.repo, "remote", "get-url", "origin", ok=(0, 2, 128))
        m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?$", url.strip()) if code == 0 else None
        if m:
            return m.group(1)
    return ""


def check_push_access(run: "Run") -> None:
    """Before any stage runs: a pipeline that ends in a pull request needs a token that can push. Found by the first
    real run — the token could clone but not push, and the run stopped at the pr step after every gate had passed.
    Asked of GitHub through gh (`permissions.push`); a gh that is absent or cannot answer never blocks the run."""
    if run.args.dry or not any(st.get("kind") == "pr" for stage in run.spec["stages"] for st in stage["steps"]):
        return
    key = github_key(run)
    if not key or not shutil.which("gh"):
        return
    r = subprocess.run(["gh", "api", f"repos/{key}", "--jq", ".permissions.push"], capture_output=True, text=True)
    if r.returncode != 0 or r.stdout.strip() not in ("true", "false"):
        return
    if r.stdout.strip() == "false":
        write_json(run.out / "needs_input.json", {"pipeline": run.spec["name"], "missing": [
            {"name": "push access", "type": "token", "from": f"the token gh uses (GH_TOKEN) can read {key} but not push to it; the pr step "
             f"pushes a branch and opens the pull request — grant it Contents: read and write and Pull requests: read and write "
             f"on {key} (fine-grained token → Repository access → select {key} → Permissions), then re-run with --resume"}]})
        sys.exit(f"error: no push access to {key} for the token gh uses — the pr step would fail after every gate passed; "
                 f"grant Contents: read and write + Pull requests: read and write on {key}, then re-run (--resume keeps the evidence)")


REPO_KEY = re.compile(r"^(?!\.)[A-Za-z0-9_-][A-Za-z0-9_.-]*/(?!\.)[A-Za-z0-9_-][A-Za-z0-9_.-]*$")


def clone_repo(key: str, dest: Path, ref: str = "") -> Path:
    """Clone owner/name into dest with gh (so GH_TOKEN or the gh login applies); reuse an existing checkout."""
    if dest.is_dir() and is_git_root(dest):
        return dest
    if not shutil.which("gh"):
        sys.exit(f"error: --repo {key} is a repository name; cloning needs the GitHub CLI (gh) on PATH, or pass a local checkout")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["gh", "repo", "clone", key, str(dest), "--", "--quiet"] + (["--branch", ref] if ref else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()
        hint = (" — the token in GH_TOKEN must have access to this repository (fine-grained token: select the repository, "
                "Contents read/write, Pull requests read/write)" if "403" in msg or "not granted" in msg or "Could not resolve" in msg else "")
        sys.exit(f"error: could not clone {key}: {msg}{hint}")
    return dest


def head_sha(repo: Path) -> str:
    """HEAD of the checkout when it is a git repository with a commit, else "" (recorded as run.json `base_sha`)."""
    if not shutil.which("git") or not is_git_root(repo):
        return ""
    code, out = git(repo, "rev-parse", "--verify", "-q", "HEAD", ok=(0, 1))
    return out.strip() if code == 0 else ""


def supersede_stale_build(spec: dict, run: "Run") -> None:
    """A resume with a DIFFERENT build/diff.patch than the one the build stage passed on: that stage and every stage
    after it are superseded — they run again on the new diff (the earlier one is taken off the checkout by the code
    step). Found by the first real run: the builder fixed the diff after the review failed, the resume kept the passed
    build stage and judged the old diff.patch again. The run record keeps the superseded verdicts under `superseded`."""
    patch = run.out / "build" / "diff.patch"
    if not patch.is_file() or run.args.builder not in ("none", "manual"):
        return
    stages = run.record.get("stages") or []
    by_id = {s["id"]: s for s in stages}
    for n, stage in enumerate(spec["stages"], 1):
        code = next((st for st in stage["steps"] if st.get("kind") == "agent" and not (st.get("produces") or [])), None)
        if not code:
            continue
        prev = by_id.get(stage["id"])
        if not prev or prev.get("status") != "passed":
            return
        rec = next((s for s in prev.get("steps", []) if s["id"] == code["id"]), {})
        evidence_patch = run.evidence / f"{n:02d}-{stage['id']}" / code["id"] / "diff.patch"
        recorded = rec.get("patch_sha256") or (sha256_file(evidence_patch) if evidence_patch.is_file() else "")
        current = sha256_file(patch)
        if not recorded or recorded == current:
            return
        later = [st["id"] for st in spec["stages"][n - 1:] if st["id"] in by_id]
        for s in stages:
            if s["id"] in later:
                s["status"] = "superseded"
                s["superseded"] = {"reason": "build/diff.patch changed after the stage passed", "previous_sha256": recorded,
                                   "sha256": current, "at": now()}
        print(f"  build/diff.patch changed since stage '{stage['id']}' passed — re-running {', '.join(later)} on the new diff")
        return


def prev_stages_status(prev_record: dict | None, stage_id: str) -> str:
    return next((st.get("status", "") for st in (prev_record or {}).get("stages") or [] if st.get("id") == stage_id), "")


def build_args(argv=None):
    ap = argparse.ArgumentParser(description="Run a delivery pipeline against a repository (see docs/DELIVERY-PIPELINES.md)")
    ap.add_argument("pipeline", nargs="?", help="pipeline name under pipelines/ or a path to its JSON")
    ap.add_argument("--pipeline", dest="pipeline_opt", metavar="NAME", help="alias of the positional pipeline argument")
    ap.add_argument("--repo", help="target repository (local checkout, or the directory to create for greenfield)")
    ap.add_argument("--request", help="the request in the requester's words")
    ap.add_argument("--brief", help="product brief JSON (optional)")
    ap.add_argument("--ref", help="branch or commit to start from")
    ap.add_argument("--input", action="append", default=[], metavar="NAME=VALUE", help="any other pipeline input (e.g. name=… for greenfield)")
    ap.add_argument("--out", help="run directory (evidence/, run.json, build/); default with --run: runs/<run id>")
    ap.add_argument("--builder", choices=["none", "manual", "claude-code"], default="none")
    ap.add_argument("--provider", choices=["dry", "none", "anthropic", "openai"], default="dry")
    ap.add_argument("--approve-all", action="store_true", help="satisfy every approval step (the invoker approves)")
    ap.add_argument("--approvals", help="JSON file recording approvals: {\"approvals\": [{\"step\": id, \"by\": name, \"note\": ...}]}")
    ap.add_argument("--patch", help="copy this diff to <out>/build/diff.patch before running (manual builder)")
    ap.add_argument("--files", help="copy this files.txt (one repo-relative path per line) to <out>/build/files.txt before running: the files step takes it when tasks.csv does not name every task's files")
    ap.add_argument("--plan", metavar="DIR", help="copy DIR/plan.md and DIR/tasks.csv (the architect's refined plan) to <out>/build/plan/ before running: the plan-refine step takes them instead of asking")
    ap.add_argument("--dry", action="store_true", help="work on a copy of the repo under <out>/repo; the pr step opens nothing")
    ap.add_argument("--resume", action="store_true", help="continue an existing run from the first incomplete stage")
    ap.add_argument("--no-baseline", action="store_true", help="do not baseline the untouched checkout before the code step: the gate skills then treat every finding as new (brownfield debt fails the gate)")
    ap.add_argument("--run-id", help="run id (default: derived from pipeline + request + repo, with a time suffix outside --dry)")
    ap.add_argument("--run", metavar="UUID", help="portal delivery run to post stage records to (with --portal; API key in env SF_API_KEY)")
    ap.add_argument("--portal", metavar="URL", help="portal base URL, e.g. https://studio.example.com")
    ap.add_argument("--approval-timeout", type=float, default=3600, metavar="SECONDS", help="portal mode: how long an approval step waits for a portal approval (default 3600)")
    ap.add_argument("--poll-interval", type=float, default=30, metavar="SECONDS", help="portal mode: seconds between approval polls (default 30)")
    args = ap.parse_args(argv)
    if args.pipeline_opt:
        if args.pipeline and args.pipeline != args.pipeline_opt:
            ap.error(f"pipeline given twice: {args.pipeline!r} and --pipeline {args.pipeline_opt!r}")
        args.pipeline = args.pipeline_opt
    if not args.pipeline:
        ap.error("a pipeline is required (positional or --pipeline)")
    if bool(args.run) != bool(args.portal):
        ap.error("--run and --portal go together")
    if args.run and not os.environ.get("SF_API_KEY"):
        ap.error("--run/--portal need the portal API key in env SF_API_KEY")
    if not args.out:
        if not args.run:
            ap.error("--out is required (or --run, which defaults it to runs/<run id>)")
        args.out = str(ROOT / "runs" / args.run)
    return args


def main(argv=None) -> int:
    args = build_args(argv)
    out = Path(args.out).expanduser().resolve()
    portal = Portal(args.portal, args.run, os.environ["SF_API_KEY"], out / "callback.log") if args.run else None
    spec, spec_path = load_pipeline(args.pipeline, portal, out)
    problems = vp.validate_pipeline(spec, vp.load_context(), spec_path.name)
    if problems:
        print(f"error: pipeline {spec_path.name} is invalid:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return EXIT_ARGS
    out.mkdir(parents=True, exist_ok=True)
    run = Run(spec, args, out)
    run.evidence.mkdir(exist_ok=True)
    run.portal = portal
    prev_record = read_json(out / "run.json") if (out / "run.json").is_file() else None
    if prev_record and not args.resume:
        print(f"error: {out / 'run.json'} exists — pass --resume to continue it or use a new --out", file=sys.stderr)
        return EXIT_ARGS
    if args.resume and not prev_record:
        print(f"error: --resume but {out / 'run.json'} does not exist", file=sys.stderr)
        return EXIT_ARGS
    for stale in ("needs_approval.json", "needs_builder.json", "wiring_error.json"):
        (out / stale).unlink(missing_ok=True)   # a resume answers the last stop; whatever stops this run writes its own

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
    for src, name in ((args.patch, "diff.patch"), (args.files, FILES_TXT)):
        if src:
            if not Path(src).is_file():
                print(f"error: {name} not found: {src}", file=sys.stderr)
                return EXIT_ARGS
            (out / "build").mkdir(exist_ok=True)
            shutil.copy(src, out / "build" / name)
    if args.plan:
        absent = [f for f in PLAN_FILES if not (Path(args.plan) / f).is_file()]
        if absent:
            print(f"error: --plan {args.plan} lacks {', '.join(absent)} (both {' and '.join(PLAN_FILES)} are needed)", file=sys.stderr)
            return EXIT_ARGS
        (out / "build" / "plan").mkdir(parents=True, exist_ok=True)
        for f in PLAN_FILES:
            shutil.copy(Path(args.plan) / f, out / "build" / "plan" / f)
    approvals = load_approvals(args.approvals)

    run.record = {"run_id": run.run_id, "pipeline": spec["name"], "version": spec.get("version", ""), "mode": spec.get("mode", ""),
                  "dry": bool(args.dry), "builder": args.builder, "provider": args.provider, "inputs": given,
                  "repo_input": repo_key, "out": str(out), "started_at": (prev_record or {}).get("started_at") or now(),
                  "resumed": bool(prev_record), "stages": list((prev_record or {}).get("stages") or [])}
    supersede_stale_build(spec, run)
    first_pending = next((st["id"] for st in spec["stages"] if prev_stages_status(run.record, st["id"]) != "passed"), spec["stages"][-1]["id"])
    try:
        prepare_repo(run)
    except StepError as e:
        print(f"error: {e}", file=sys.stderr)
        run.save("failed", EXIT_FAIL)
        run.post_stage({"id": first_pending, "status": "failed", "error": f"prepare repo: {e}"[:4000]}, started_at=now(), finished_at=now())
        return EXIT_FAIL
    run.record["repo"] = str(run.repo)
    run.record["base_sha"] = (prev_record or {}).get("base_sha") or head_sha(run.repo)   # the pre-change commit, kept across resumes
    run.load_baseline()

    prev_stages = {s["id"]: s for s in run.record["stages"]}
    # restore step dirs of stages already passed (references into them must resolve on resume)
    for n, stage in enumerate(spec["stages"], 1):
        for step in stage["steps"]:
            run.step_dirs[step["id"]] = run.evidence / f"{n:02d}-{stage['id']}" / step["id"]
    profile_after = (spec.get("stack_profile") or {}).get("after")
    try:
        if not profile_after or prev_stages.get(profile_after, {}).get("status") == "passed":
            run.read_profile()
            run.post_profile(first_pending)
        elif (run.evidence / "stack-profile.json").is_file():
            run.profile = read_json(run.evidence / "stack-profile.json")
    except StepError as e:
        print(f"error: {e}", file=sys.stderr)
        run.save("failed", EXIT_FAIL)
        run.post_stage({"id": first_pending, "status": "failed", "error": f"stack profile: {e}"[:4000]}, started_at=now(), finished_at=now())
        return EXIT_FAIL
    for n, stage in enumerate(spec["stages"], 1):
        prev = prev_stages.get(stage["id"])
        if prev and prev.get("status") == "passed":
            continue
        status, code = run.run_stage(n, stage, prev, approvals)
        run.save(status, code)
        run.post_stage_result(next(st for st in run.record["stages"] if st["id"] == stage["id"]))
        if code != EXIT_OK:
            nb = read_json(out / "needs_builder.json") if code == EXIT_BUILDER and (out / "needs_builder.json").is_file() else {}
            where = {EXIT_APPROVAL: f"needs approval — see {out / 'needs_approval.json'}",
                     EXIT_BUILDER: f"needs the {nb.get('role') or 'builder'} ({nb.get('step', '?')}) — see {out / 'needs_builder.json'}",
                     EXIT_ARGS: f"pipeline wiring error — see {out / 'wiring_error.json'}"}.get(code, "gate failed — see " + str(run.evidence / f"{n:02d}-{stage['id']}" / "gate.json"))
            print(f"{spec['name']} run {run.run_id}: stopped at stage '{stage['id']}' ({status}): {where}")
            if code == EXIT_ARGS:
                we = read_json(out / "wiring_error.json")
                print(f"error: {we['message']}", file=sys.stderr)
            return code
        if profile_after == stage["id"]:
            try:
                if args.dry:
                    baseline_commit(run.repo)
                run.read_profile()
                nxt = spec["stages"][n]["id"] if n < len(spec["stages"]) else stage["id"]
                run.post_profile(nxt)
            except StepError as e:
                print(f"error: {e}", file=sys.stderr)
                run.save("failed", EXIT_FAIL)
                run.post_stage({"id": stage["id"], "status": "failed", "error": f"stack profile: {e}"[:4000]}, finished_at=now())
                return EXIT_FAIL
        print(f"  stage {stage['id']}: {status} — {run.record['stages'][-1]['gate']['detail'][:120]}")
    run.save("passed", EXIT_OK)
    print(f"{spec['name']} run {run.run_id}: {len(spec['stages'])} stages passed — evidence in {run.evidence / 'EVIDENCE.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
