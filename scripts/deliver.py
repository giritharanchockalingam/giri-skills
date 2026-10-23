#!/usr/bin/env python3
"""Run a delivery pipeline (pipelines/<name>.json) against a real repository — docs/DELIVERY-PIPELINES.md.

    python3 scripts/deliver.py feature-delivery --repo ./app --request "Export orders as CSV" \
        [--brief brief.json] [--ref main] [--input name=value ...] --out ./runs/r1 \
        --builder none|manual|claude-code|openai-compat [--model NAME --base-url URL --rounds N --repair-cmd CMD] \
        [--install auto|none|CMD] [--tests auto|none|CMD] [--provider dry|none|anthropic|openai] \
        [--approve-all | --approvals approvals.json] [--patch diff.patch] [--files files.txt] [--plan DIR] [--prd prd-final.md] [--dry] [--resume] [--run-id ID] \
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
            --builder openai-compat -> the packet is sent to any OpenAI-compatible chat endpoint (scripts/llm_builder.py:
                                     --base-url / OPENAI_BASE_URL, --model / OPENAI_MODEL, OPENAI_API_KEY) and the model's
                                     `=== FILE: … ===` blocks are the step's output: written to the step folder for
                                     prd-refine / plan-refine / files, into the checkout (allowed files + test paths) for
                                     the code step, where --repair-cmd (default: the resolved --tests command) runs and a
                                     failure goes back as a repair turn, up to --rounds (2); evidence: llm-rounds.json,
                                     llm-reply-<n>.txt; run.json step `llm`
            every builder, code step: the checkout's dependencies are installed once per run before the code lands
            (--install auto: `npm ci` / `npm install` / pnpm / yarn / bun / pip / uv / poetry from the stack profile;
            <step>/install.log + install.json; node_modules and .venv are kept out of the diff via .git/info/exclude
            when .gitignore does not cover them) and the project's tests are EXECUTED after the code landed (--tests
            auto: the package manager's `test` script, `npx vitest run` / `npx jest`, `pytest -q`; <step>/tests.json
            with cmd, exit, duration, summary and the output tail + tests.log). A failing test command fails the code
            step (the StepError quotes the tail, so the gate detail says the tests failed); for openai-compat the
            failing output is the repair turn first, up to --rounds. Both are skipped (recorded as such) in --dry and
            when the repository has no runner. EVIDENCE.md carries a Tests line ("tests: N passed") and the build
            row links tests.json / tests.log / install.log.
            every exit-4 stop (prd-refine, plan-refine, files, code) also writes <step dir>/PROMPT.md — the role
            packet (Run.role_packet): role, outputs and paths, the gate checks verbatim, every input inlined, the
            role's SKILL.md and the resume command — for ANY agent or a person; needs_builder.json `prompt` names
            it, and the claude-code builder's prompt.txt is the same text
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
import llm_builder  # noqa: E402
import validate_pipelines as vp  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_ARGS, EXIT_APPROVAL, EXIT_BUILDER = 0, 1, 2, 3, 4
TBD_RE = re.compile(r"\[TO BE BASELINED[^\]]*\]")
GIT_ENV = {"GIT_AUTHOR_NAME": "deliver", "GIT_AUTHOR_EMAIL": "deliver@giri-skills.local",
           "GIT_COMMITTER_NAME": "deliver", "GIT_COMMITTER_EMAIL": "deliver@giri-skills.local",
           "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
COPY_IGNORE = shutil.ignore_patterns("node_modules", ".next", "dist", "coverage", ".turbo", "__pycache__", ".venv")
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
PRD_MD = "prd-final.md"                              # what the prd-refine step produces (see step_prd_refine)
PLAN_COLUMNS = ["id", "task", "acceptance", "test", "rollback", "files", "size", "repo_check"]   # spec-to-plan's tasks.csv
PLAN_FILLED = ("acceptance", "test", "files")       # a scaffold is complete when none of these is TBD or empty in any task
# skills whose `baseline` input is a findings.csv of recorded debt, and the stack-profile check each one is wired from
BASELINE_SKILLS = {"build/nextjs-enterprise-conventions": "nextjs", "build/perf-review-runner": "perf",
                   "build/ui-component-quality": "ui", "build/tech-debt-audit-runner": "debt"}
BASELINE_DIR = "00-baseline"                        # <out>/evidence/00-baseline/<skill>/findings.csv — the pre-change findings
NEW_HIGH_LISTED = 10                                # gate detail: the full count, the first 10 findings, "… and M more"
GATE_DETAIL_LIMIT = 1200                            # the count comes first, so a long list never hides it
TEST_PATH_RE = llm_builder.TEST_PATH_RE                     # test files the code step may add beside files.txt (one definition)
PACKET_MD = "PROMPT.md"                             # the role packet every builder stop writes (see Run.role_packet)
PACKET_INLINE_LIMIT = 40 * 1024                     # an input this size or smaller is inlined whole in the packet
PACKET_HEAD_LINES = 60                              # a larger one: its first lines + "(truncated)"
# the SKILL.md that backs a role step, inlined in its packet (the code step inlines its constraint docs instead)
PACKET_SKILLS = {PRD_MD: "skills/build/product-spec-prd/SKILL.md", TASKS_CSV: "skills/build/spec-to-plan/SKILL.md"}
# the code step installs the checkout's dependencies once per run and executes the project's tests after the code
# lands, for every builder (found by the first local-model run: the clone had no node_modules, the repair command
# resolved to nothing and the PR's CI was the first place the model's code was ever run)
INSTALL_TIMEOUT_S = 900                             # 15 min for npm ci / pip install
TEST_TIMEOUT_S = 1800                               # 30 min for the project's test command
TEST_TAIL = 4 * 1024                                # tests.json carries the last 4 KB of the runner's output
TEST_TAIL_IN_ERROR = 400                            # how much of that the step error (the gate detail) quotes
INSTALL_DIRS = ("node_modules", ".venv")            # never part of the diff or the PR: excluded via .git/info/exclude when .gitignore does not
TESTS_JSON, TESTS_LOG, INSTALL_JSON, INSTALL_LOG = "tests.json", "tests.log", "install.json", "install.log"
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class StepError(Exception):
    pass


def _read_pkg(target: Path) -> dict:
    pkg = target / "package.json"
    if not pkg.is_file():
        return {}
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def install_cmd(profile: dict, target: Path) -> str | None:
    """How the checkout's dependencies are installed, from the stack profile's package_manager and the manifests on
    disk — or None when there is nothing to install. npm: `npm ci` with a package-lock.json, else `npm install`;
    pnpm / yarn frozen when their lockfile is there; bun; Python: uv / poetry / pipenv, else pip from
    requirements.txt or `pip install -e .` from a pyproject.toml."""
    pm = str(profile.get("package_manager") or "unknown")
    if (target / "package.json").is_file():
        if pm == "pnpm":
            return "pnpm install --frozen-lockfile" if (target / "pnpm-lock.yaml").is_file() else "pnpm install"
        if pm == "yarn":
            return "yarn install --frozen-lockfile" if (target / "yarn.lock").is_file() else "yarn install"
        if pm == "bun":
            return "bun install"
        return "npm ci" if (target / "package-lock.json").is_file() else "npm install --no-audit --no-fund"
    if pm == "uv":
        return "uv sync"
    if pm == "poetry":
        return "poetry install"
    if pm == "pipenv":
        return "pipenv install --dev"
    if (target / "requirements.txt").is_file():
        return "python3 -m pip install -r requirements.txt"
    if str(profile.get("flavour")) == "python" and (target / "pyproject.toml").is_file():
        return "python3 -m pip install -e ."
    return None


def test_cmd(profile: dict, target: Path) -> str | None:
    """The project's own test command, from the stack profile and package.json — or None when the repository has no
    runner. Node: the package manager's `test` script when package.json declares one (`vitest run` in the fixture
    and the bootstrap skeleton), else the detected runner directly (`npx vitest run` / `npx jest`); Python: pytest
    through uv / poetry / pipenv when that is the package manager, else `python3 -m pytest -q`."""
    pm = str(profile.get("package_manager") or "unknown")
    runner = str(profile.get("test_runner") or "none")
    pkg = _read_pkg(target)
    if pkg or (target / "package.json").is_file():
        if (pkg.get("scripts") or {}).get("test"):
            return {"pnpm": "pnpm test", "yarn": "yarn test", "bun": "bun run test"}.get(pm, "npm test")
        if runner == "vitest":
            return "npx vitest run"
        if runner == "jest":
            return "npx jest"
        return None
    if runner == "pytest":
        return {"uv": "uv run pytest -q", "poetry": "poetry run pytest -q", "pipenv": "pipenv run pytest -q"}.get(pm, "python3 -m pytest -q")
    return None


def test_summary(output: str) -> str:
    """`N passed[, M failed[, K skipped]]` read best-effort from a vitest (`Tests  2 passed (2)`) or pytest
    (`3 passed, 1 failed in 0.4s`) summary line; "" when the runner printed none (the exit code is the verdict)."""
    text = ANSI_RE.sub("", output or "")
    parts = []
    for word in ("passed", "failed", "skipped"):
        found = re.findall(rf"(\d+)\s+{word}\b", text)
        if found:
            parts.append(f"{found[-1]} {word}")
    return ", ".join(parts)


def output_tail(text: str, limit: int) -> str:
    text = ANSI_RE.sub("", text or "")
    return text if len(text) <= limit else "…" + text[-limit:]


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
    """One task for spec-to-plan: the task line, then one indented `- <field>: <value>` line per field. Nested lines
    (not the inline `(accept: …; test: …)` form) because real acceptance text carries parentheses and semicolons —
    found by the first greenfield run, where every task came back TBD."""
    lines = [f"- {text}"]
    for k, v in fields.items():
        v = " ".join(str(v).split())
        if v:
            lines.append(f"  - {k}: {v}")
    return "\n".join(lines)


def prd_stories(md: str) -> list[dict]:
    """The PRD's 'User stories and acceptance criteria' section as tasks: one per `### S<n> — … I want: <what>` (or
    `### S<n> — <what>`) heading, acceptance from its `Then …` and test from `Verified by: …`. Template placeholders
    (`<persona>`, `…`, TBD markers) yield nothing — those stories are not written yet."""
    sec = re.search(r"^##\s+[^\n]*user stories[^\n]*\n(.*?)(?=^##\s|\Z)", md, re.I | re.M | re.S)
    if not sec:
        return []
    out: list[dict] = []
    for block in re.split(r"^###\s+", sec.group(1), flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        head = re.sub(r"^S\d+\s*[—-]\s*", "", head.strip())
        what = re.sub(r"^As [^,]+,\s*I want:?\s*", "", head, flags=re.I).strip().rstrip(".")
        then = re.search(r"\bThen\s+(.+)", body)
        accept = then.group(1).strip() if then else ""
        test = re.search(r"Verified by:\s*(.+)", body)
        text = what + " " + accept
        if not what or re.search(r"<[a-z][a-z /_-]*>|…|TO BE BASELINED", text):
            continue
        out.append({"task": what, "accept": accept, "test": test.group(1).strip() if test else ""})
    return out


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
    if not bullets and inputs.get("prd") and Path(str(inputs["prd"])).is_file():
        # the product manager's PRD: its user stories (S1..Sn with Then … / Verified by …) are the tasks
        stories = prd_stories(Path(str(inputs["prd"])).read_text(encoding="utf-8", errors="replace"))
        if stories:
            source = "prd.stories"
            bullets = [_task_bullet(st["task"], {"accept": st.get("accept", ""), "test": st.get("test", ""), "files": files_all}) for st in stories]
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
        self._llm = None   # the openai-compat client, built on first use (see llm_client)
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

    # ---- the role packet: what every builder stop hands to ANY agent (docs/DELIVERY-PIPELINES.md → The role packet)
    def role_packet(self, step: dict, need: dict, inputs: list[dict], skill: str = "") -> str:
        """<step dir>/PROMPT.md — a self-contained Markdown packet a developer pastes into any agent (Cursor, Copilot,
        Claude Code, a local model) or reads themselves, whatever --builder is. One text for every builder: the
        claude-code builder's prompt.txt is this same packet, so the two never drift. `need` is the needs_builder.json
        record for the stop (expected / alternative / format / rule / why / how, allowed_files, constraints);
        `inputs` is an ordered list of {"label", "path"} or {"label", "text"} — a text file of PACKET_INLINE_LIMIT bytes
        or less is inlined whole under a fence, a larger one as its first PACKET_HEAD_LINES lines + "(truncated)";
        `skill` is the SKILL.md (repo-relative) that backs the role, inlined when given. Deterministic, no secrets:
        nothing from the environment but sys.argv (the resume command)."""
        step_id = step["id"]
        role = str(need.get("role") or "builder")

        def fenced(text: str) -> list[str]:
            runs = re.findall(r"`{3,}", text)
            fence = "`" * (max((len(r) for r in runs), default=2) + 1)
            return [fence, text.rstrip("\n"), fence]

        def inline(p: str) -> list[str]:
            path = Path(p) if p else None
            if not path or not path.is_file():
                return ["_(missing)_"]
            raw = path.read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                return [f"_(binary, {len(raw)} bytes — not inlined)_"]
            if len(raw) <= PACKET_INLINE_LIMIT:
                return fenced(text)
            head = "\n".join(text.splitlines()[:PACKET_HEAD_LINES])
            return fenced(head) + ["", f"_(truncated — {len(raw)} bytes; the first {PACKET_HEAD_LINES} lines are shown; read the file at the path above)_"]

        def as_map(v) -> dict:
            if isinstance(v, dict):
                return {str(k): str(x) for k, x in v.items()}
            produce = need.get("produce")
            name = produce[0] if isinstance(produce, list) and produce else str(produce or Path(str(v)).name)
            return {name: str(v)} if v else {}

        def gate_lines(gate: dict) -> tuple[list[str], list[str]]:
            """(checks on this step's outputs, verbatim as eval_gate evaluates them; the rest of the stage gate)."""
            mine, rest = [], []
            kind = gate.get("kind")
            if kind == "output":
                line = f"{gate.get('file')}: {gate.get('check')}"
                if gate.get("step") == step_id:
                    mine.append(line)
                else:
                    rest.append(f"output of step '{gate.get('step')}' — {line}")
            elif kind in ("all", "any"):
                for g in gate.get("of") or []:
                    m, r = gate_lines(g)
                    mine += m
                    rest += r
                if kind == "any" and (gate.get("of") or []):
                    rest.append("(the parts above are combined with `any`: one passing part passes the stage)")
            elif kind == "exit":
                rest.append(f"exit — step '{gate.get('step')}' must exit 0" + (" (it judges this step's output)" if gate.get("step") != step_id else ""))
            elif kind == "approval":
                rest.append(f"approval — step '{gate.get('step')}' must be approved")
            elif kind == "external":
                rest.append(f"external — {gate.get('what', '')}")
            return mine, rest

        stage = next((s for s in self.spec["stages"] if s["id"] == need.get("stage")), {})
        mine, rest = gate_lines(stage.get("gate") or {})
        expected, alternative = as_map(need.get("expected")), as_map(need.get("alternative"))

        lines = [f"# Role: {role} — step {step_id} (run {self.run_id}, pipeline {self.spec['name']})", "",
                 f"Stage `{need.get('stage')}` of pipeline `{self.spec['name']}` stopped at step `{step_id}` for the {role}. "
                 f"This packet is self-contained: paste it into any agent, or do the work yourself.", "",
                 *([f"Why: {need['why']}", ""] if need.get("why") else []),
                 "## What to produce", ""]
        for name, p in expected.items():
            lines.append(f"- `{name}` → write it at `{p}`" + (f" (or drop it at `{alternative[name]}`)" if alternative.get(name) else ""))
        if not expected:
            lines.append(f"- {need.get('produce', '')}")
        if need.get("target"):
            lines.append(f"- Repository checkout: `{need['target']}` (read it; the code step is the only one that changes it)")
        for key, label in (("format", "Format"), ("rule", "Rule"), ("how", "How")):
            if need.get(key):
                lines += ["", f"**{label}:** {need[key]}"]
        lines += ["", "## The gate this must pass", ""]
        if mine:
            lines += ["Checks the executor runs on this step's outputs, exactly as it evaluates them (`<file>: <check>`); a failing check refuses the stage:", ""]
            lines += [f"- `{m}`" for m in mine]
        else:
            lines.append("No output check runs on this step's files directly.")
        if rest:
            lines += ["", "Also in the stage gate:", ""] + [f"- {r}" for r in rest]
        lines += ["", "## Inputs", ""]
        for item in inputs:
            lines.append(f"### {item['label']}" + (f" — `{item['path']}`" if item.get("path") else ""))
            lines.append("")
            lines += fenced(item["text"]) if "text" in item else inline(item.get("path", ""))
            lines.append("")
        if need.get("allowed_files") is not None:
            lines += [f"### Files you may touch (from {need.get('allowed_files_source', 'the plan')})", ""]
            lines += [f"- `{f}`" for f in need["allowed_files"]] or ["(none listed: the plan names the files)"]
            lines += ["", "Plus the test files the test plan names. Nothing else.", ""]
        for c in need.get("constraints") or []:
            lines += [f"### Constraint — `{c}`", ""] + inline(c) + [""]
        if self.record.get("stack_profile"):
            lines += ["### Stack profile", ""] + fenced(json.dumps(self.record["stack_profile"], indent=2)) + [""]
        lines += ["## Role skill", ""]
        if skill:
            lines += [f"The skill that backs this role — `{ROOT / skill}`:", ""] + inline(str(ROOT / skill)) + [""]
        elif need.get("constraints"):
            lines += ["The constraint documents under Inputs are the rules this step follows; no further skill backs it.", ""]
        else:
            lines += ["None: the format and rule above are the whole brief.", ""]
        argv = [str(Path(sys.argv[0]).resolve())] + [a for a in sys.argv[1:] if a != "--resume"] + ["--resume"]
        lines += ["## When done", "",
                  "Write the output(s) at the expected path(s) above, do not commit, then resume the run:", "",
                  "```", shlex.join([sys.executable or "python3"] + argv), "```", ""]
        return "\n".join(lines)

    def write_packet(self, step: dict, sdir: Path, need: dict, inputs: list[dict], skill: str = "") -> str:
        """Write <step dir>/PROMPT.md, point needs_builder.json at it (need['prompt']) and return the packet text."""
        packet = self.role_packet(step, need, inputs, skill)
        (sdir / PACKET_MD).write_text(packet, encoding="utf-8")
        need["prompt"] = str(sdir / PACKET_MD)
        return packet

    # ---- the openai-compat builder: the packet goes to any OpenAI-compatible model (scripts/llm_builder.py)
    def llm_client(self) -> "llm_builder.OpenAICompat":
        """One client per run, built from --model / --base-url and the OPENAI_* environment; a misconfiguration is a
        StepError before any call (the same guard main() applies up front)."""
        if self._llm is None:
            try:
                self._llm = llm_builder.OpenAICompat(self.args.model, self.args.base_url)
            except llm_builder.OpenAICompatError as e:
                raise StepError(f"builder openai-compat: {e}") from None
        return self._llm

    def builder_label(self) -> str:
        """`openai-compat (<model> @ <host>)` for the evidence header; the builder name otherwise."""
        if self.args.builder != "openai-compat":
            return self.args.builder
        try:
            c = self.llm_client()
        except StepError:
            return f"openai-compat ({self.args.model or os.environ.get('OPENAI_MODEL') or '?'})"
        return f"openai-compat ({c.model} @ {c.host})"

    def repair_cmd(self, target: Path, tests: str | None) -> str | None:
        """The command the openai-compat code step runs after each round of the model's files, whose failing output is
        the next repair turn. --repair-cmd CMD as given; `none` → no repair loop (the resolved test command still runs
        once after the model's last reply, and fails the step); `auto` (default) → the resolved test command."""
        given = (self.args.repair_cmd or "").strip()
        if given.lower() in ("", "none", "off"):
            return None
        return tests if given == "auto" else given

    # ---- the code step's deterministic gates: install once, run the project's tests (every builder)
    def resolve_install(self, target: Path) -> tuple[str | None, str]:
        """(command, reason-when-none) for --install auto|none|<cmd>. `auto` reads the stack profile (install_cmd);
        a dry run installs nothing (the copy is throwaway and offline-reproducible)."""
        given = (getattr(self.args, "install", "auto") or "auto").strip()
        if given.lower() in ("none", "off"):
            return None, "--install none"
        if given != "auto":
            return given, ""
        if self.args.dry:
            return None, "dry run"
        cmd = install_cmd(self.profile, target)
        return cmd, ("" if cmd else "no package manifest (nothing to install)")

    def resolve_tests(self, target: Path) -> tuple[str | None, str]:
        """(command, reason-when-none) for --tests auto|none|<cmd>. `auto` reads the stack profile (test_cmd); a dry
        run skips (its copy has no dependencies installed; an explicit --tests <cmd> still runs there)."""
        given = (getattr(self.args, "tests", "auto") or "auto").strip()
        if given.lower() in ("none", "off"):
            return None, "--tests none"
        if given != "auto":
            return given, ""
        if self.args.dry:
            return None, "dry run"
        cmd = test_cmd(self.profile, target)
        return cmd, ("" if cmd else "no runner")

    @staticmethod
    def exclude_install_dirs(target: Path) -> list[str]:
        """node_modules / .venv must never enter the diff or the PR (`git add -A`): when the checkout's .gitignore does
        not cover them, add them to .git/info/exclude — local to the clone, never a change to the repository."""
        if not shutil.which("git") or not is_git_root(target):
            return []
        added = []
        code, path = git(target, "rev-parse", "--git-path", "info/exclude", ok=(0, 128))
        if code != 0:
            return []
        exclude = Path(path.strip())
        if not exclude.is_absolute():
            exclude = target / exclude
        for d in INSTALL_DIRS:
            ignored, _ = git(target, "check-ignore", "-q", d, ok=(0, 1, 128))
            if ignored == 1:
                exclude.parent.mkdir(parents=True, exist_ok=True)
                with exclude.open("a", encoding="utf-8") as fh:
                    fh.write(f"{d}/\n")
                added.append(d)
        return added

    @staticmethod
    def _sh(cmd: str, cwd: Path, timeout_s: float) -> tuple[int, str]:
        env = {**os.environ, "CI": os.environ.get("CI") or "1"}   # watch-mode runners (vitest, jest) run once under CI
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s, env=env)
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired as e:
            partial = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            return 124, f"timed out after {timeout_s:.0f}s\n{partial}"

    def install_deps(self, target: Path, sdir: Path, rec: dict) -> None:
        """Once per run, in the checkout, before the code lands: the stack profile's install command, its output in
        <step>/install.log, the record in install.json and run.json `install`. A resume reuses a successful install
        (install.json with exit 0 and the same command). A failing install fails the code step: the tests cannot run."""
        cmd, reason = self.resolve_install(target)
        prev = read_json(sdir / INSTALL_JSON) if (sdir / INSTALL_JSON).is_file() else {}
        if cmd and prev.get("cmd") == cmd and prev.get("exit") == 0:
            rec["install"] = {**prev, "reused": True}
            return
        excluded = self.exclude_install_dirs(target)   # even without an install: a developer's node_modules must not be staged
        if not cmd:
            rec["install"] = {"skipped": reason}
            write_json(sdir / INSTALL_JSON, rec["install"])
            return
        t0 = time.time()
        code, output = self._sh(cmd, target, INSTALL_TIMEOUT_S)
        (sdir / INSTALL_LOG).write_text(output, encoding="utf-8")
        info = {"cmd": cmd, "exit": code, "duration_s": round(time.time() - t0, 3), "log": INSTALL_LOG}
        if excluded:
            info["excluded_from_git"] = excluded
        write_json(sdir / INSTALL_JSON, info)
        rec["install"] = info
        if code != 0:
            raise StepError(f"install failed: `{cmd}` exit {code} (see {INSTALL_LOG}); tail: {output_tail(output, TEST_TAIL_IN_ERROR)!r}")

    def record_tests(self, sdir: Path, rec: dict, info: dict) -> None:
        write_json(sdir / TESTS_JSON, info)
        rec["tests"] = {k: v for k, v in info.items() if k != "tail"}

    def run_tests(self, cmd: str | None, reason: str, target: Path, sdir: Path, rec: dict) -> None:
        """After the code landed: the project's test command on the checkout, its output in <step>/tests.log, the
        record (cmd, exit, duration_s, summary, tail) in tests.json and run.json `tests`. Exit != 0 fails the code
        step — the StepError names the summary and the output tail, so the gate detail says the tests failed."""
        if not cmd:
            self.record_tests(sdir, rec, {"skipped": reason})
            return
        t0 = time.time()
        code, output = self._sh(cmd, target, TEST_TIMEOUT_S)
        (sdir / TESTS_LOG).write_text(output, encoding="utf-8")
        info = {"cmd": cmd, "exit": code, "duration_s": round(time.time() - t0, 3), "summary": test_summary(output),
                "tail": output_tail(output, TEST_TAIL), "log": TESTS_LOG}
        self.record_tests(sdir, rec, info)
        if code != 0:
            raise StepError(f"tests failed: `{cmd}` exit {code}" + (f" ({info['summary']})" if info["summary"] else "")
                            + f"; tail: {output_tail(output, TEST_TAIL_IN_ERROR)!r}")

    def record_llm_tests(self, cmd: str, sdir: Path, rec: dict) -> None:
        """openai-compat: the repair command IS the test command, already run by the builder after each round — the
        last round's result becomes tests.json (its log is that round's llm-cmd-<n>.txt)."""
        rounds = (read_json(sdir / "llm-rounds.json") if (sdir / "llm-rounds.json").is_file() else {}).get("rounds") or []
        last = next((r for r in reversed(rounds) if "cmd_exit" in r), None)
        if last is None:
            self.record_tests(sdir, rec, {"skipped": "the model's rounds ran no command"})
            return
        log = f"llm-cmd-{last['round']}.txt"
        output = (sdir / log).read_text(encoding="utf-8", errors="replace") if (sdir / log).is_file() else ""
        self.record_tests(sdir, rec, {"cmd": cmd, "exit": last["cmd_exit"], "duration_s": last.get("cmd_duration_s"),
                                      "summary": test_summary(output), "tail": output_tail(output, TEST_TAIL), "log": log,
                                      "rounds": last["round"]})

    def step_output_checks(self, step_id: str) -> list[tuple[str, str]]:
        """The stage gate's output checks on this step's files, as (file, check) — what the model's documents are
        held to after each round (the same checks eval_gate runs), so a refusal is answered inside the builder."""
        stage = next((st for st in self.spec["stages"] if any(x["id"] == step_id for x in st["steps"])), None)
        out: list[tuple[str, str]] = []

        def walk(g: dict) -> None:
            if g.get("kind") == "output" and g.get("step") == step_id and g.get("file") and g.get("check"):
                out.append((str(g["file"]), str(g["check"])))
            for sub in g.get("of") or []:
                walk(sub)
        if stage:
            walk(stage.get("gate") or {})
        return out

    def run_llm_role(self, sdir: Path, rec: dict, packet: str, *, produce: list[str], allowed: list[str] | None,
                     target: Path | None, repair_cmd: str | None = None, step_id: str = "", extra_check=None) -> dict:
        """Send the packet to the model and land its file blocks (llm_builder.run_role); the step record gets `llm`
        {provider, model, base_url_host, rounds}. A reply that parses to nothing, or a repair command still failing
        after --rounds, is a StepError that names the reply head — the gate detail then says what the model did."""
        client = self.llm_client()
        t0 = time.time()
        try:
            checks = self.step_output_checks(step_id) if (target is None and step_id) else []
            res = llm_builder.run_role(packet, produce=produce, allowed=allowed, out_dir=sdir, target=target, client=client,
                                       max_rounds=self.args.rounds, repair_cmd=repair_cmd,
                                       checks=checks, check_fn=lambda path, spec: check_output.run_check(spec, str(path), mode="real"),
                                       extra_check=extra_check)
        except llm_builder.LLMBuildError as e:
            rec["llm"] = {"provider": "openai-compat", "model": client.model, "base_url_host": client.host,
                          "rounds": len((read_json(sdir / "llm-rounds.json") if (sdir / "llm-rounds.json").is_file() else {}).get("rounds") or []),
                          "duration_s": round(time.time() - t0, 3), "ok": False}
            raise StepError(f"builder openai-compat ({client.model} @ {client.host}): {e}") from None
        rec["llm"] = {"provider": "openai-compat", "model": client.model, "base_url_host": client.host,
                      "rounds": res["rounds"], "duration_s": round(time.time() - t0, 3), "ok": True}
        return res

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
        need = {"run_id": self.run_id, "pipeline": self.spec["name"], "stage": rec["stage"], "step": step["id"],
                "builder": builder, "target": str(target), "plan": plan, "tasks": tasks or None,
                "why": f"files.txt could not be derived: {why}",
                "produce": FILES_TXT, "expected": str(expected), "alternative": str(dropped),
                "format": "one repo-relative path per line (source files the change will create or modify; test files are not "
                          "needed — the tests step adds them); blank lines and `#` comments are ignored",
                "rule": "read plan.md / tasks.csv and the checkout; list only files the plan's tasks require; nothing invented; "
                        "do not change any file in the repository",
                "how": f"write {FILES_TXT} at the expected path (or pass --files <file>), then re-run with --resume"}
        packet_inputs = [{"label": "plan.md", "path": plan}] + ([{"label": TASKS_CSV, "path": tasks}] if tasks else [])
        if builder in ("none", "manual"):
            rec["status"] = "awaiting_builder"
            self.write_packet(step, sdir, need, packet_inputs)
            write_json(self.out / "needs_builder.json", need)
            return False
        if builder == "claude-code":
            exe = shutil.which("claude")
            if not exe:
                raise StepError("builder claude-code: `claude` is not on PATH (install Claude Code, or use --builder manual with files.txt)")
            prompt = self.write_packet(step, sdir, need, packet_inputs)   # prompt.txt is the packet: one source for every builder
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
        if builder == "openai-compat":
            prompt = self.write_packet(step, sdir, need, packet_inputs)   # the packet is what the model gets
            res = self.run_llm_role(sdir, rec, prompt, produce=[FILES_TXT], allowed=None, target=None, step_id=step["id"])
            if not expected.is_file():
                raise StepError(f"builder openai-compat did not write {expected}")
            return record(read_files_txt(expected), "openai-compat",
                          f"written by {res['model']} @ {res['base_url_host']} in {res['rounds']} round(s) at {expected.relative_to(self.out)}")
        raise StepError(f"unknown builder {builder!r}")

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

    def repo_layout(self, target: Path, limit: int = 400) -> str:
        """What the architect must see before naming files: the stack profile facts and the checkout's tracked paths
        (bounded). Found on the first local-model run — the model planned src/*.ts in a JavaScript app-router repo."""
        prof = self.record.get("stack_profile") or self.profile or {}
        facts = ", ".join(f"{k}={prof.get(k)}" for k in ("flavour", "framework", "package_manager", "test_runner", "e2e", "migrations_dir", "monorepo_root") if prof.get(k) not in (None, "", "none", "unknown"))
        paths: list[str] = []
        if shutil.which("git") and is_git_root(target):
            code, out = git(target, "ls-files", ok=(0, 128))
            paths = [ln for ln in out.splitlines() if ln.strip()] if code == 0 else []
        if not paths and target.is_dir():
            for root, dirs, files in os.walk(target):
                dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".next", ".venv", "__pycache__", "dist", "build"}]
                for f in files:
                    paths.append(str(Path(root, f).relative_to(target)))
        paths.sort()
        shown = paths[:limit]
        tops = sorted({p.split("/")[0] for p in paths})
        lines = [f"Stack profile: {facts or 'unknown'}", f"Top-level entries: {', '.join(tops) or '(empty repository)'}",
                 f"Tracked files ({len(paths)}{', first ' + str(limit) + ' shown' if len(paths) > limit else ''}):"] + [f"  {p}" for p in shown]
        lines.append("Rule: every file a task names is a path in THIS layout — an existing file to modify, or a new file in an "
                     "existing directory with the repository's language and framework conventions (same extension as its neighbours).")
        return "\n".join(lines)

    @staticmethod
    def plan_fits_repo(tasks_path: str, target: Path, profile: dict) -> list[str]:
        """Files the plan names that cannot be right for this checkout: a parent directory that does not exist (a layout
        the model invented, e.g. src/ in an app-router repo), or an extension that contradicts the stack flavour
        (.ts in a JavaScript repo and vice versa). Empty list = the plan fits."""
        if not tasks_path or not Path(tasks_path).is_file():
            return []
        rows = list(csv.DictReader(io.StringIO(Path(tasks_path).read_text(encoding="utf-8"))))
        flavour = str((profile or {}).get("flavour") or "")
        has_any = any(target.rglob("*")) if target.is_dir() else False
        problems: list[str] = []
        for r in rows:
            for f in [repo_path(x) for x in re.split(r"[,;]+", r.get("files") or "") if repo_path(x)]:
                if TBD_RE.search(f):
                    continue
                p = target / f
                ext = Path(f).suffix.lower()
                if flavour == "js" and ext in (".ts", ".tsx"):
                    problems.append(f"{r.get('id') or '?'}: {f} is TypeScript but the repository is JavaScript (flavour js)")
                elif flavour == "ts" and ext in (".js", ".jsx") and not p.is_file():
                    problems.append(f"{r.get('id') or '?'}: {f} is JavaScript but the repository is TypeScript (flavour ts)")
                if has_any and not p.exists():
                    top = f.split("/")[0]
                    if "/" in f and not (target / top).is_dir():
                        problems.append(f"{r.get('id') or '?'}: {f} is under {top}/, which does not exist in the repository (invented layout)")
        return problems

    def step_prd_refine(self, step: dict, sdir: Path, rec: dict) -> bool:
        """The product manager's step (agent step producing prd-final.md): the PRD draft from the brief is taken as
        is when its user stories / acceptance criteria are filled (a brief with stories or tasks); otherwise the run
        stops for the product manager — exit 4, needs_builder.json role 'product-manager' — who writes prd-final.md
        at the expected path. Found by the first greenfield run: a request with no brief produced a template PRD
        that the requirements gate waved through, and the architect planned against nothing."""
        builder = self.args.builder
        rec["builder"] = builder
        draft = str(self.resolve(step["inputs"].get("prd"), "prd-refine prd"))
        request = str(self.resolve(step["inputs"].get("request", ""), "prd-refine request") or self.inputs.get("request", ""))
        expected = sdir / PRD_MD
        dropped = self.out / "build" / "prd" / PRD_MD
        if not expected.is_file() and dropped.is_file():
            shutil.copy(dropped, expected)
        if expected.is_file():
            rec.update(exit=0, prd_source="product-manager")
            write_json(sdir / "prd-refine.json", {"source": "product-manager", "skipped": False, "draft": draft})
            return True
        verdict = check_output.run_check('section_filled:"user stories"', draft, mode="real")
        if verdict.get("pass"):
            shutil.copy(draft, expected)
            rec.update(exit=0, prd_source="draft", skipped=True)
            write_json(sdir / "prd-refine.json", {"source": "draft", "skipped": True, "draft": draft, "note": verdict.get("evidence")})
            return True
        rec["status"] = "awaiting_builder"
        need = {"run_id": self.run_id, "pipeline": self.spec["name"], "stage": rec["stage"], "step": step["id"],
                "role": "product-manager", "builder": builder, "prd": draft, "request": request,
                "why": "the PRD draft has no acceptance criteria: " + str(verdict.get("evidence")),
                "produce": [PRD_MD], "expected": {PRD_MD: str(expected)}, "alternative": {PRD_MD: str(dropped)},
                "format": "the draft with every [TO BE BASELINED] cell the request answers filled, and the 'User stories and "
                          "acceptance criteria' section written as S1..Sn with Given/When/Then lines (nothing invented beyond the request)",
                "rule": "fill the PRD from the request and what the requester can confirm; mark what you cannot know "
                        "[TO BE BASELINED — owner: <role>] outside the stories; the gate refuses stories with TBD or template placeholders",
                "how": f"write {PRD_MD} at the expected path, then re-run with --resume"}
        try:
            brief_path = str(self.resolve(step["inputs"].get("brief", ""), "prd-refine brief") or "")
        except StepError:
            brief_path = ""   # the brief is context for the packet, never a reason to fail the stop
        packet_inputs = [{"label": "Request", "text": request or "(none)"}, {"label": f"Draft PRD ({PRD_MD})", "path": draft}]
        if brief_path:
            packet_inputs.append({"label": "Brief (brief.json)", "path": brief_path})
        if builder == "openai-compat":
            rec["status"] = "ok"   # not a stop: the model answers the packet now
            prompt = self.write_packet(step, sdir, need, packet_inputs, PACKET_SKILLS[PRD_MD])
            res = self.run_llm_role(sdir, rec, prompt, produce=[PRD_MD], allowed=None, target=None, step_id=step["id"])
            if not expected.is_file():
                raise StepError(f"builder openai-compat did not write {expected}")
            rec.update(exit=0, prd_source="openai-compat")
            write_json(sdir / "prd-refine.json", {"source": "openai-compat", "skipped": False, "draft": draft,
                                                  "note": f"written by {res['model']} @ {res['base_url_host']} in {res['rounds']} round(s)"})
            return True
        self.write_packet(step, sdir, need, packet_inputs, PACKET_SKILLS[PRD_MD])
        write_json(self.out / "needs_builder.json", need)
        return False

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
            misfit = self.plan_fits_repo(str(expected[TASKS_CSV]), target, self.record.get("stack_profile") or self.profile or {})
            if misfit:
                raise StepError(f"{TASKS_CSV} from {source} names files that do not fit the repository: " + "; ".join(misfit[:4])
                                + " — name existing files or new files in existing directories with the repository's conventions")
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
        need = {"run_id": self.run_id, "pipeline": self.spec["name"], "stage": rec["stage"], "step": step["id"],
                "role": "architect", "builder": builder, "target": str(target),
                "plan": scaffold_plan, "tasks": scaffold_tasks, "prd": prd or None, "request": request,
                "why": "the scaffold plan is not a plan yet: " + "; ".join(gaps[:8]) + (" …" if len(gaps) > 8 else ""),
                "produce": list(PLAN_FILES),
                "expected": {f: str(expected[f]) for f in PLAN_FILES},
                "alternative": {f: str(dropped[f]) for f in PLAN_FILES},
                "format": f"{TASKS_CSV}: columns {','.join(PLAN_COLUMNS)}; files repo-relative, comma-separated; repo_check "
                          f"`<file>: create|modify` per the checkout; {PLAN_MD}: the scaffold with its file table and every task "
                          "block filled (Files, Acceptance, Tests, Rollback); keep the scaffold's structure and task ids",
                "rule": "read the scaffold plan, the PRD and the checkout; fill the file table and every task's acceptance, test, "
                        "rollback and files; nothing invented beyond what the PRD and the request state — where they are silent, "
                        "say so in the task text rather than guessing; the gate refuses any [TO BE BASELINED cell in acceptance, "
                        "test or files; do not change any file in the repository",
                "how": f"write both files at the expected paths (or pass --plan <dir> holding {PLAN_MD} and {TASKS_CSV}), then re-run with --resume"}
        packet_inputs = [{"label": "Gaps the gate will refuse", "text": "\n".join(f"- {g}" for g in gaps)},
                         {"label": "Request", "text": request or "(none)"}, {"label": f"PRD ({PRD_MD})", "path": prd},
                         {"label": "Repository layout (name files that fit it)", "text": self.repo_layout(target)},
                         {"label": f"Scaffold {PLAN_MD}", "path": scaffold_plan}, {"label": f"Scaffold {TASKS_CSV}", "path": scaffold_tasks}]
        if builder in ("none", "manual"):
            rec["status"] = "awaiting_builder"
            self.write_packet(step, sdir, need, packet_inputs, PACKET_SKILLS[TASKS_CSV])
            write_json(self.out / "needs_builder.json", need)
            return False
        if builder == "claude-code":
            exe = shutil.which("claude")
            if not exe:
                raise StepError("builder claude-code: `claude` is not on PATH (install Claude Code, or use --builder manual with --plan <dir>)")
            prompt = self.write_packet(step, sdir, need, packet_inputs, PACKET_SKILLS[TASKS_CSV])   # one source for every builder
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
        if builder == "openai-compat":
            prompt = self.write_packet(step, sdir, need, packet_inputs, PACKET_SKILLS[TASKS_CSV])
            prof = self.record.get("stack_profile") or self.profile or {}
            res = self.run_llm_role(sdir, rec, prompt, produce=list(PLAN_FILES), allowed=None, target=None, step_id=step["id"],
                                    extra_check=lambda d: self.plan_fits_repo(str(d / TASKS_CSV), target, prof))
            absent = [f for f in PLAN_FILES if not expected[f].is_file()]
            if absent:
                raise StepError(f"builder openai-compat did not write {', '.join(str(expected[f]) for f in absent)}")
            return record("openai-compat", f"written by {res['model']} @ {res['base_url_host']} in {res['rounds']} round(s) at {sdir.relative_to(self.out)}")
        raise StepError(f"unknown builder {builder!r}")

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
        if PRD_MD in produces:
            return self.step_prd_refine(step, sdir, rec)
        builder = self.args.builder
        rec["builder"] = builder
        plan = str(self.resolve(step["inputs"].get("plan"), "agent plan"))
        tests = str(self.resolve(step["inputs"].get("tests", ""), "agent tests") or "")
        files = str(self.resolve(step["inputs"].get("files", ""), "agent files") or "")
        target = Path(str(self.resolve(step["inputs"].get("target", "$repo"), "agent target")))
        allowed, allowed_source = self._allowed_files(plan, files)
        rec["allowed_files"] = allowed
        manual_patch = self.out / "build" / "diff.patch"
        need = {"run_id": self.run_id, "pipeline": self.spec["name"], "stage": rec["stage"], "step": step["id"],
                "builder": builder, "target": str(target), "plan": plan, "tests": tests, "files": files or None,
                "allowed_files": allowed, "allowed_files_source": allowed_source,
                "constraints": [str(ROOT / c) for c in step.get("constraints") or []],
                "rule": f"touch only the files {allowed_source} names (plus the test files the test plan names); make the red tests "
                        "green; follow every constraint document; do not refactor, rename or reformat anything else; do not commit",
                "produce": "diff.patch", "expected": str(manual_patch),
                "how": "write the code on the checkout, save `git diff` (staged + unstaged, new files included) to the "
                       "expected path (or pass --patch <file>), then re-run with --resume"}
        packet_inputs = [{"label": "Plan (plan.md)", "path": plan}, {"label": "Test plan (test-plan.md)", "path": tests}]
        if builder in ("none", "manual"):
            if manual_patch.is_file():
                rec["patch_sha256"] = sha256_file(manual_patch)
                self._revert_superseded_patch(manual_patch, target, sdir, rec)
                self.install_deps(target, sdir, rec)              # the project's tests need its dependencies
                if self.args.dry:  # the checkout is a throwaway copy: land the diff so the lint stages assess the change
                    note = self._apply_to_copy(manual_patch, target)
                else:              # the real checkout: the diff is what the gates and the PR must see
                    note = self._apply_manual(manual_patch, target, allowed, allowed_source, sdir, rec)
                self._record_diff(manual_patch, sdir, rec, plan, f"Diff supplied at build/diff.patch (builder: {builder}); {note}", files)
                self.run_tests(*self.resolve_tests(target), target, sdir, rec)   # the project's tests judge the diff
                return True
            rec["status"] = "awaiting_builder"
            self.write_packet(step, sdir, need, packet_inputs)
            write_json(self.out / "needs_builder.json", need)
            return False
        if builder == "claude-code":
            exe = shutil.which("claude")
            if not exe:
                raise StepError("builder claude-code: `claude` is not on PATH (install Claude Code, or use --builder manual with build/diff.patch)")
            if not is_git_root(target):
                raise StepError(f"builder claude-code: {target} is not a git repository root; the diff cannot be captured")
            prompt = self.write_packet(step, sdir, need, packet_inputs)   # one source for every builder
            (sdir / "prompt.txt").write_text(prompt, encoding="utf-8")
            self.install_deps(target, sdir, rec)                  # before the agent: it may run the tests itself
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
            self.run_tests(*self.resolve_tests(target), target, sdir, rec)   # the project's tests judge the agent's code
            return True
        if builder == "openai-compat":
            if not is_git_root(target):
                raise StepError(f"builder openai-compat: {target} is not a git repository root; the diff cannot be captured")
            prompt = self.write_packet(step, sdir, need, packet_inputs)   # one source for every builder
            self.install_deps(target, sdir, rec)                  # before the first round: the repair command needs the dependencies
            tcmd, treason = self.resolve_tests(target)
            cmd = self.repair_cmd(target, tcmd)                   # default: the test command is the repair loop
            try:
                res = self.run_llm_role(sdir, rec, prompt, produce=[], allowed=allowed or None, target=target, repair_cmd=cmd)
            except StepError:
                if cmd and cmd == tcmd:                           # the rounds are spent: the last run is the test record
                    self.record_llm_tests(cmd, sdir, rec)
                raise
            git(target, "add", "-A")
            _, diff = git(target, "diff", "--cached", "--binary")
            if not diff.strip():
                raise StepError(f"builder openai-compat ({res['model']}): the model's files left the checkout unchanged (wrote {res['files'] or 'nothing'})")
            patch = sdir / "captured.patch"
            patch.write_text(diff, encoding="utf-8")
            summary = (f"Written by {res['model']} @ {res['base_url_host']} in {res['rounds']} round(s); files: "
                       + (", ".join(res["files"]) or "none") + (f"; deleted: {', '.join(res['deleted'])}" if res.get("deleted") else "")
                       + (f"; `{cmd}` exit {res.get('cmd_exit')}" if cmd else "; no repair command ran"))
            self._record_diff(patch, sdir, rec, plan, summary, files)
            patch.unlink()
            if cmd and cmd == tcmd:
                self.record_llm_tests(cmd, sdir, rec)             # the repair loop already ran the tests (exit 0 here)
            else:                                                 # --repair-cmd none or an override: the tests run once, now
                self.run_tests(tcmd, treason, target, sdir, rec)
            return True
        raise StepError(f"unknown builder {builder!r}")

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
        # The push authenticates as gh does (GH_TOKEN, or the gh login) and as nothing else: on a developer machine the
        # OS keychain (osxkeychain, manager) usually holds an older github.com credential that git would try first and
        # GitHub would answer 403 with, whatever the token in GH_TOKEN may do. `-c credential.helper=` empties the
        # helper list for this one command; gh's helper is then the only one.
        push_cfg = PUSH_CFG if shutil.which("gh") else []
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
        push = subprocess.run(["git", *push_cfg, "push", "-u", "origin", branch], cwd=str(repo), capture_output=True, text=True, env=env)
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
                f"mode {self.spec.get('mode', '')} · builder {self.builder_label()} · provider {self.args.provider}"
                + (" · DRY RUN" if self.args.dry else ""), "",
                f"Request: {self.inputs.get('request', '')}", "",
                "Stack profile: " + ", ".join(f"{k}={v}" for k, v in (self.record.get("stack_profile") or {}).items()), "",
                self.baseline_row(), "",
                self.tests_row(), "",
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

    def tests_row(self) -> str:
        """The Tests line of EVIDENCE.md: what the code step executed on the checkout after the code landed —
        `tests: N passed` when the runner printed a summary, else the exit code; `tests: skipped (<reason>)`."""
        code = next((st for s in self.record.get("stages", []) for st in s.get("steps", [])
                     if st.get("kind") == "agent" and "tests" in st), None)
        if not code:
            return "Tests (after the change): not run yet — executed by the build stage's code step, every builder."
        t = code["tests"]
        if t.get("skipped"):
            return f"Tests (after the change): tests: skipped ({t['skipped']})."
        sdir = self.step_dirs.get(code["id"])
        log = sdir / str(t.get("log") or "") if sdir else None
        link = f" — [{log.name}]({log.relative_to(self.evidence)})" if log and log.is_file() else ""
        verdict = f"tests: {t['summary']}" if t.get("summary") else f"tests: exit {t.get('exit')}"
        install = code.get("install") or {}
        inst = (f"; install `{install['cmd']}` exit {install['exit']}" if install.get("cmd") else
                f"; install skipped ({install['skipped']})" if install.get("skipped") else "")
        return f"Tests (after the change): `{t.get('cmd')}` exit {t.get('exit')} — {verdict}{link}{inst}."

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
        if (prev or {}).get("status") == "failed":
            # a model-written document that the gate refused is not "supplied by the product manager/architect": it is
            # removed before the step runs again, so the model gets another turn instead of the stale file being
            # re-judged (found on the first local-model run). Files a person dropped (manual) are never touched.
            if self.args.builder in ("openai-compat", "claude-code"):
                drops = {PRD_MD: self.out / "build" / "prd" / PRD_MD, PLAN_MD: self.out / "build" / "plan" / PLAN_MD,
                         TASKS_CSV: self.out / "build" / "plan" / TASKS_CSV, FILES_TXT: self.out / "build" / FILES_TXT}
                for st in stage["steps"]:
                    if st.get("kind") != "agent":
                        continue
                    for name in st.get("produces") or []:
                        if not drops.get(name, Path("/nonexistent")).is_file():   # a person's drop wins over the model
                            (stage_dir / st["id"] / name).unlink(missing_ok=True)
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
                        who = ("architect (the refined plan.md / tasks.csv)" if TASKS_CSV in (step.get("produces") or [])
                               else "product manager (prd-final.md with acceptance criteria)" if PRD_MD in (step.get("produces") or []) else "builder")
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
        # the code step's own evidence — what the executor ran on the checkout (install, the project's tests) — travels
        # with the stage whatever the template's evidence list says: tests.json and its log, install.json and its log
        for st in stage.get("steps") or []:
            if st.get("kind") != "agent" or st.get("produces"):
                continue
            sdir = self.step_dirs.get(st["id"])
            if not sdir or not sdir.is_dir():
                continue
            for name in (TESTS_JSON, INSTALL_JSON):
                info = read_json(sdir / name) if (sdir / name).is_file() else None
                if info is None:
                    continue
                for p in (sdir / name, sdir / str(info.get("log") or "")):
                    if p.is_file():
                        rel = str(p.relative_to(self.evidence))
                        if rel not in files:
                            files.append(rel)
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
        if run.spec.get("mode") == "greenfield" and REPO_KEY.match(str(run.inputs["repo"])):
            # greenfield named owner/name: the repository is created on GitHub (private) when it does not exist,
            # cloned under the run either way; the bootstrap stage then makes its first commit on main
            src = create_or_clone_repo(str(run.inputs["repo"]), run.out / "repo", run)
        elif run.spec.get("mode") == "greenfield":
            src.mkdir(parents=True, exist_ok=True)
        elif REPO_KEY.match(str(run.inputs["repo"])):
            # the portal names repositories owner/name: clone it under the run (the token in GH_TOKEN, via gh)
            src = clone_repo(str(run.inputs["repo"]), run.out / "repo", str(run.inputs.get("ref") or ""))
        else:
            sys.exit(f"error: --repo {src} is not a directory (give a local checkout, or owner/name to clone it)")
    run.repo = src.resolve()
    if run.spec.get("mode") == "greenfield" and shutil.which("git"):
        if not is_git_root(run.repo):
            git(run.repo, "init", "-q", "-b", "main")
        elif not head_sha(run.repo):   # a clone of an empty repository has no branch yet
            git(run.repo, "checkout", "-q", "-B", "main", ok=(0, 128))
    if run.inputs.get("ref") and is_git_root(run.repo):
        git(run.repo, "checkout", "-q", str(run.inputs["ref"]))
    check_push_access(run)


def create_or_clone_repo(key: str, dest: Path, run: "Run") -> Path:
    """Greenfield on GitHub: `gh repo view` says whether owner/name exists; if not, `gh repo create --private` makes
    it (the token needs repository-creation rights — the gh login, or a classic token with `repo`); then the usual
    clone. Recorded on the run (`repo_created`) so the evidence says the run made the repository."""
    if dest.is_dir() and is_git_root(dest):
        return dest
    if not shutil.which("gh"):
        sys.exit(f"error: --repo {key} names a GitHub repository; creating or cloning it needs the GitHub CLI (gh) on PATH")
    exists = subprocess.run(["gh", "api", f"repos/{key}", "--jq", ".name"], capture_output=True, text=True).returncode == 0   # REST, works where GraphQL is blocked
    if not exists:
        r = subprocess.run(["gh", "repo", "create", key, "--private", "--description", f"created by giri-skills {run.spec['name']}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"error: could not create {key}: {(r.stderr or r.stdout).strip()[:300]} — create it empty on GitHub yourself "
                     "(private), or use a token that may create repositories, then re-run")
        run.record["repo_created"] = key
    return clone_repo(key, dest)


def commit_bootstrap(run: "Run") -> None:
    """Greenfield, after the bootstrap stage: the scaffold becomes the first commit on main (pushed when there is an
    origin), so the feature the later stages build is a pull request ON TOP of a reviewable base rather than a PR
    against nothing. base_sha is that commit. Idempotent: a repository that already has a commit is left alone."""
    repo = run.repo
    if run.args.dry or run.spec.get("mode") != "greenfield" or not shutil.which("git") or not is_git_root(repo):
        return
    env = {**os.environ, **BOT_GIT_ENV, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    git(repo, "add", "-A", env=env)
    _, dirty = git(repo, "status", "--porcelain", env=env)
    if head_sha(repo) and not dirty.strip():
        return   # nothing new from the bootstrap stage (a repository that already carries the scaffold)
    # a repository with earlier commits still gets its scaffold additions committed to main (second greenfield run,
    # or a repository that held a README): the feature PR carries the feature, not the skeleton
    git(repo, "commit", "-q", "-m", f"bootstrap: {run.inputs.get('name') or repo.name}", "-m",
        f"Scaffold by giri-skills pipeline {run.spec['name']} run {run.run_id}", env=env)
    sha = head_sha(repo)
    run.record["base_sha"] = sha
    code, _ = git(repo, "remote", "get-url", "origin", ok=(0, 2, 128), env=env)
    if code == 0:
        cfg = PUSH_CFG if shutil.which("gh") else []
        push = subprocess.run(["git", *cfg, "push", "-u", "origin", "main"], cwd=str(repo), capture_output=True, text=True, env=env)
        if push.returncode != 0:
            raise StepError(f"bootstrap commit could not be pushed to origin main: {(push.stderr or push.stdout).strip()[:300]}")
    run.record["bootstrap_commit"] = sha


def github_key(run: "Run") -> str:
    """owner/name of the repository the pr step will push to: the --repo key, or the origin remote of the checkout."""
    key = str(run.inputs.get("repo") or "")
    if REPO_KEY.match(key):
        return key
    if shutil.which("git") and is_git_root(run.repo):
        code, url = git(run.repo, "remote", "get-url", "origin", ok=(0, 2, 128))
        m = re.search(r"[:/]([^/\s:]+/[^/\s:]+?)(?:\.git)?/?$", url.strip()) if code == 0 and "://" in url or ":" in url else None
        if m:
            return m.group(1)
    return ""


PUSH_CFG = ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]   # authenticate as gh does, only


def check_push_access(run: "Run") -> None:
    """Before any stage runs: a pipeline that ends in a pull request needs a token that can push. Found by the first
    real run — the token could clone but not push, and the run stopped at the pr step after every gate had passed.
    Asked the only reliable way, a `git push --dry-run` of HEAD to the delivery branch (GitHub refuses receive-pack
    with 403 for a token without Contents: write; `permissions.push` on the repo describes the user, not a fine-grained
    token). Nothing is written to the remote. A push that fails for any other reason (offline, no origin) never blocks."""
    if run.args.dry or not any(st.get("kind") == "pr" for stage in run.spec["stages"] for st in stage["steps"]):
        return
    key = github_key(run)
    if not key or not shutil.which("git") or not is_git_root(run.repo) or not head_sha(run.repo):
        return
    cfg = PUSH_CFG if shutil.which("gh") else []
    r = subprocess.run(["git", *cfg, "push", "--dry-run", "origin", f"HEAD:refs/heads/deliver/{run.run_id}"], cwd=str(run.repo),
                       capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    why = (r.stderr or r.stdout).strip()
    if r.returncode == 0 or not ("403" in why or "not granted" in why or "Permission" in why or "denied" in why.lower()):
        return
    write_json(run.out / "needs_input.json", {"pipeline": run.spec["name"], "missing": [
        {"name": "push access", "type": "token", "from": f"the token gh uses (GH_TOKEN) can read {key} but not push to it "
         f"(git push --dry-run: {why[:160]}); the pr step pushes a branch and opens the pull request — grant the token "
         f"Contents: read and write and Pull requests: read and write on {key} (fine-grained token → Repository access → "
         f"select {key} → Permissions), then re-run with --resume"}]})
    sys.exit(f"error: no push access to {key} for the token gh uses ({why.splitlines()[0][:120]}) — the pr step would fail after every "
             f"gate passed; grant Contents: read and write + Pull requests: read and write on {key}, then re-run (--resume keeps the evidence)")


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
    if r.returncode != 0 and not dest.exists():
        # gh repo clone needs GraphQL, which some proxies refuse: plain git over HTTPS with gh's credential helper
        r = subprocess.run(["git", *PUSH_CFG, "clone", "--quiet", f"https://github.com/{key}.git", str(dest)] + (["--branch", ref] if ref else []),
                           capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
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
    ap.add_argument("--builder", choices=["none", "manual", "claude-code", "openai-compat"], default="none")
    ap.add_argument("--model", help="openai-compat builder: the model name (default: env OPENAI_MODEL)")
    ap.add_argument("--base-url", help="openai-compat builder: the endpoint base, e.g. http://localhost:11434/v1 (default: env OPENAI_BASE_URL, else api.openai.com)")
    ap.add_argument("--rounds", type=int, default=2, metavar="N", help="openai-compat builder: model turns per step including repair turns (default 2)")
    ap.add_argument("--repair-cmd", default="auto", metavar="CMD", help="openai-compat builder: shell command run on the checkout after each round of the code step's files; a failure is sent back as a repair turn. Default auto: the resolved --tests command; `none` runs no repair loop (the tests still run once after the last reply)")
    ap.add_argument("--install", default="auto", metavar="auto|none|CMD", help="code step, every builder: install the checkout's dependencies once per run before the code lands (output in <step>/install.log). auto (default): from the stack profile — `npm ci` with a package-lock.json else `npm install --no-audit --no-fund`, pnpm/yarn/bun, pip/uv/poetry for Python; nothing in --dry. `none` skips; any other value runs as given")
    ap.add_argument("--tests", default="auto", metavar="auto|none|CMD", help="code step, every builder: the project's test command, executed on the checkout after the code lands (tests.json + tests.log in the step dir); a failure fails the code step (openai-compat: it is the repair turn first). auto (default): from the stack profile — the package manager's `test` script, `npx vitest run` / `npx jest`, `pytest -q`; skipped (recorded) in --dry or when the repository has no runner. `none` skips; any other value runs as given")
    ap.add_argument("--provider", choices=["dry", "none", "anthropic", "openai"], default="dry")
    ap.add_argument("--approve-all", action="store_true", help="satisfy every approval step (the invoker approves)")
    ap.add_argument("--approvals", help="JSON file recording approvals: {\"approvals\": [{\"step\": id, \"by\": name, \"note\": ...}]}")
    ap.add_argument("--patch", help="copy this diff to <out>/build/diff.patch before running (manual builder)")
    ap.add_argument("--prd", help="copy this prd-final.md (the PRD with its user stories / acceptance criteria filled) to <out>/build/prd/ before running: the prd-refine step takes it instead of stopping for the product manager")
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
    if args.builder == "openai-compat":
        try:   # the guard runs before any call: a non-OpenAI model name with no base URL would go to api.openai.com
            llm_builder.OpenAICompat(args.model, args.base_url)
        except llm_builder.OpenAICompatError as e:
            print(f"error: builder openai-compat: {e}", file=sys.stderr)
            return EXIT_ARGS
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
    for src, name, sub in ((args.patch, "diff.patch", ""), (args.files, FILES_TXT, ""), (args.prd, PRD_MD, "prd")):
        if src:
            if not Path(src).is_file():
                print(f"error: {name} not found: {src}", file=sys.stderr)
                return EXIT_ARGS
            (out / "build" / sub).mkdir(parents=True, exist_ok=True)
            shutil.copy(src, out / "build" / sub / name)
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
                commit_bootstrap(run)
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
