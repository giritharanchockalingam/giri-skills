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
gate failure) · 3 waiting for an approval (needs_approval.json; also a run `reject` marked rejected, until the step
is approved again) · 4 waiting for the builder (needs_builder.json).
Stdlib only; deterministic apart from the timestamps in run.json.

Local mode (docs/DELIVERY-PIPELINES.md → Local mode (no portal)) — the run registry without a portal, no network:
    deliver.py list [--runs DIR] [--json]                      runs under $SF_RUNS_DIR (default runs/), from each <out>/run.json
    deliver.py status <out|run id> [--json]                    stage table, the current stop, the resume command
    deliver.py approve <out|run id> --step ID --by NAME [--note …]   writes <out>/approvals.json (read by the next --resume)
    deliver.py reject <out|run id> --step ID --by NAME --note …     writes <out>/rejections.json, marks the run rejected
    deliver.py audit <out|run id> [--json|--md]                <out>/evidence/provenance.json (skills + versions + sha256,
                                                               executor sha, pipeline sha, approvals, rejections, gates)
Every status change appends a line to <runs dir>/registry.jsonl. scripts/mcp_local.py exposes the same over MCP.
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
import skillmeta  # noqa: E402
import sandbox as sbx  # noqa: E402
import telemetry  # noqa: E402
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
# Top-level directories shared/stack-conventions.md defines (plus the test folders test-strategy-tdd writes): a plan may
# create them even when the checkout does not have them yet. Found on greenfield G1/G3: server/services and
# supabase/migrations were refused as "invented layout" although they are this stack's own conventions. src/ stays
# out — in an app-router repo it IS the invented layout this check exists for.
CONVENTION_DIRS = frozenset({"app", "components", "lib", "server", "supabase", "tests", "e2e", "public", "scripts", "docs", "types", "hooks", "styles"})
PLAN_FILES = (PLAN_MD, TASKS_CSV)                   # what the plan-refine step produces (see step_plan_refine)
PRD_MD = "prd-final.md"                              # what the prd-refine step produces (see step_prd_refine)
PLAN_COLUMNS = ["id", "task", "acceptance", "test", "rollback", "files", "size", "repo_check"]   # spec-to-plan's tasks.csv
PLAN_FILLED = ("acceptance", "test", "files")       # a scaffold is complete when none of these is TBD or empty in any task
# skills whose `baseline` input is a findings.csv of recorded debt, and the stack-profile check each one is wired from
BASELINE_SKILLS = {"build/nextjs-enterprise-conventions": "nextjs", "build/perf-review-runner": "perf",
                   "build/ui-component-quality": "ui", "build/tech-debt-audit-runner": "debt"}
NONINTERACTIVE_RULES = ("You are running non-interactively inside a delivery pipeline: nobody can answer questions or approve "
                        "anything. Shell commands are not available. Inspect with Read, Grep and Glob; create and change files "
                        "only with Write and Edit, writing every file the task asks for at the exact paths given. Do not write "
                        "helper scripts. Where something is unknown, record it in the file as the task's rules say instead of "
                        "asking. The pipeline itself runs the project's tests, then `npm run bench` when package.json "
                        "defines a `bench` script, then opens the app in a browser: a benchmark must be self-contained (it "
                        "creates, migrates and seeds whatever it needs from the environment, e.g. DATABASE_URL) and writes its "
                        "own results file; never write results you did not measure. "
                        "Finish by writing the files, then reply with one short summary.")
REVIEWER_RULES = ("You are an independent reviewer running non-interactively inside a delivery pipeline. You did not write "
                  "this code and you have not seen its author's notes. Judge whether it meets the acceptance criteria. Be "
                  "skeptical: verify by reading code and running things, never by trusting docs, comments, test names or "
                  "commit messages. Nobody can answer questions. Finish by writing the JSON file you are asked for.")
BASELINE_DIR = "00-baseline"                        # <out>/evidence/00-baseline/<skill>/findings.csv — the pre-change findings
NEW_HIGH_LISTED = 10                                # gate detail: the full count, the first 10 findings, "… and M more"
GATE_DETAIL_LIMIT = 1200                            # the count comes first, so a long list never hides it
TEST_PATH_RE = llm_builder.TEST_PATH_RE                     # test files the code step may add beside files.txt (one definition)
TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|e2e)/")   # test files the code step may add beside files.txt
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
ACCEPT_DIR, ACCEPT_JSON, ACCEPT_MD, ACCEPT_TIMEOUT_S = "acceptance", "acceptance.json", "acceptance.md", 2400
VERDICTS = ("MET", "PARTLY", "NOT_MET", "UNVERIFIED")
BENCH_LOG, BENCH_TIMEOUT_S = "bench.log", 900                       # `npm run bench`, run by the pipeline (see run_bench)
VISUAL_DIR, VISUAL_TIMEOUT_S, VISUAL_MAX_ROUTES = "visual", 900, 6   # scripts/visual_check.py: a person's first look
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# local mode (docs/DELIVERY-PIPELINES.md → Local mode): the run registry and the local approval files, no portal needed
REGISTRY_JSONL = "registry.jsonl"                   # <runs dir>/registry.jsonl — one line per status change of every run
APPROVALS_JSON, REJECTIONS_JSON = "approvals.json", "rejections.json"   # <out>/…, written by `deliver.py approve|reject`
PROVENANCE_JSON = "provenance.json"                 # <out>/evidence/provenance.json — skills, versions, hashes, approvals, gates
LOCAL_COMMANDS = ("list", "status", "approve", "reject", "audit")
SKILL_HASH_IGNORE = {"__pycache__", "runs", ".DS_Store"}   # never part of a skill's fingerprint (local, gitignored)


def runs_dir() -> Path:
    """Where runs live by default and where registry.jsonl is kept: SF_RUNS_DIR, else runs/ under giri-skills."""
    return Path(os.environ.get("SF_RUNS_DIR") or (ROOT / "runs")).expanduser()


def registry_append(entry: dict) -> None:
    """One line per status change — the local audit trail. Never aborts a run (a read-only runs dir is a warning)."""
    try:
        d = runs_dir()
        d.mkdir(parents=True, exist_ok=True)
        with (d / REGISTRY_JSONL).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as e:
        print(f"warning: registry {runs_dir() / REGISTRY_JSONL} not written: {e}", file=sys.stderr)


_SKILL_FP: dict[str, dict] = {}


def skill_fingerprint(skill: str) -> dict:
    """{name, version, sha256, path} of a library skill (`build/spec-to-plan`): the name and version from its SKILL.md
    frontmatter, the sha256 of the skill directory's contents — every file under it, sorted by relative posix path,
    each hashed as `<path>\\0<bytes>\\0` — so the same skill tree gives the same hash on every machine."""
    if skill in _SKILL_FP:
        return _SKILL_FP[skill]
    sdir = ROOT / "skills" / skill
    info = {"skill": skill, "name": skill.rsplit("/", 1)[-1], "version": "", "sha256": "", "path": str(sdir.relative_to(ROOT))}
    if sdir.is_dir():
        md = sdir / "SKILL.md"
        if md.is_file():
            try:
                fm = skillmeta.parse_frontmatter(md.read_text(encoding="utf-8"))
                info["name"] = str(fm.get("name") or info["name"])
                meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
                info["version"] = str(meta.get("version") or fm.get("version") or "")
            except Exception:   # a frontmatter the subset parser cannot read: the hash still stands
                pass
        h = hashlib.sha256()
        files = []
        for p in sdir.rglob("*"):
            if p.is_file() and not (set(p.relative_to(sdir).parts) & SKILL_HASH_IGNORE) and p.suffix != ".pyc":
                files.append(p)
        for p in sorted(files, key=lambda x: x.relative_to(sdir).as_posix()):
            h.update(p.relative_to(sdir).as_posix().encode("utf-8") + b"\0" + p.read_bytes() + b"\0")
        info["sha256"] = h.hexdigest()
        info["files"] = len(files)
    else:
        info["error"] = "skill directory not found"
    _SKILL_FP[skill] = info
    return info


_EXECUTOR_SHA: str | None = None


def executor_sha() -> str:
    """HEAD of the giri-skills checkout this executor runs from, "" when it is not a git checkout."""
    global _EXECUTOR_SHA
    if _EXECUTOR_SHA is None:
        _EXECUTOR_SHA = ""
        if shutil.which("git") and (ROOT / ".git").exists():
            r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True)
            if r.returncode == 0:
                _EXECUTOR_SHA = r.stdout.strip()
    return _EXECUTOR_SHA



RULE_RE = re.compile(r'^\s*"([A-Z]{2,3}\d+)":\s*\("([^"]+)",\s*"(high|medium|low)",\s*"((?:[^"\\]|\\.)*)"', re.M)


def gate_rules_section(spec: dict) -> str:
    """The rules the later gate skills will judge the change by, for the code step's packet. Found live on tradesignal:
    the builder wrote `.select('*', { count: 'exact' })`, the perf gate (PF3) failed the run after the code was done.
    A builder told the rules before it writes avoids that. Read from each gate skill's own rule table, so the packet
    never drifts from what the gates enforce; a skill whose table cannot be read is simply not listed."""
    gate_skills = []
    for st in spec.get("stages", []):
        for step in st.get("steps", []):
            if step.get("kind") == "skill" and step.get("skill") in BASELINE_SKILLS and step["skill"] not in gate_skills:
                gate_skills.append(step["skill"])
    lines = []
    for skill in gate_skills:
        for script in sorted((ROOT / "skills" / skill / "scripts").glob("*.py")):
            rows = RULE_RE.findall(script.read_text(encoding="utf-8", errors="replace"))
            if rows:
                lines.append(f"\n**{skill}** (high blocks the run; medium is reported):")
                lines += [f"- {rid} {name} ({sev}): {desc.replace(chr(92) + chr(34), chr(34))}" for rid, name, sev, desc in rows]
                break
    review = ROOT / "skills" / "build" / "code-review-runner" / "scripts" / "review.py"
    if review.is_file():   # the review gate: "CR-X": ("blocking"|"warning"|"info", "what", "fix")
        rows = re.findall(r'^\s*"(CR-[A-Z-]+)":\s*\("(blocking|warning|info)",\s*"([^"]+)",\s*"([^"]+)"', review.read_text(encoding="utf-8"), re.M)
        if rows:
            lines.append("\n**build/code-review-runner** (blocking fails the run):")
            lines += [f"- {rid} ({sev}): {what} — {fix}" for rid, sev, what, fix in rows]
    lines.append("\n**build/security-review** (critical/high fail the run): authorization on every route; no SQL text built "
                 "from variables; secrets only from the environment; no server fetch to a caller-supplied URL; no raw HTML from "
                 "data; no service-role access from client code.")
    lines.append("\n**SQL text is never assembled from variables, not even an allow-listed table name.** Both the review "
                 "(CR-SQL-CONCAT) and the security scan (SEC2) block a template literal such as `select * from ${table}`. When a "
                 "statement must vary by table, keep one constant SQL string per table in a map keyed by the allow-listed name "
                 "and look it up (found on the CAPE sync spike: 9 blocking findings on allow-listed identifiers).")
    if not lines:
        return ""
    return ("\n\n## Rules the gates will apply to your change\n\nAfter you finish, these checks run on the lines you add or "
            "change. A new high finding fails the run, even on a line you only edited (keep `select('*')` and the gate "
            "counts it as yours). Write the change so none of them fire:\n" + "\n".join(lines) + "\n")


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


class ReviewerError(StepError):
    """The acceptance reviewer itself failed (no valid acceptance.json): never sent to the builder as a repair."""


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


def now_precise() -> str:
    """Approvals and rejections are ordered by their timestamps; within one second (a CLI approve right after a
    reject, or a test) second resolution cannot order them, so these carry microseconds (still sortable as text)."""
    import datetime as _dt
    return _dt.datetime.now().isoformat(timespec="microseconds")


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
        self.spec_path: Path | None = None   # the pipeline file this run executes (hashed into provenance.json)
        self._tracer: telemetry.Tracer | None = None   # docs/HARNESS.md layer 5 (see the tracer property)
        self._stage_span = self._step_span = None
        self._exported = ""

    @property
    def tracer(self) -> "telemetry.Tracer":
        """One OTLP trace per run invocation: a span per stage, step and model call (evidence/trace.json)."""
        if self._tracer is None:
            self._tracer = telemetry.Tracer("deliver", self.run_id or "pending", **{"pipeline": self.spec.get("name", ""),
                                            "builder": getattr(self.args, "builder", ""), "dry": bool(getattr(self.args, "dry", False))})
        return self._tracer

    def _close_step_span(self, rec: dict | None) -> None:
        if self._step_span is not None:
            r = rec or {}
            self.tracer.end(self._step_span, error=(str(r.get("error"))[:300] if r.get("status") == "failed" else None),
                            **{"step.status": r.get("status"), "step.repairs": len(r.get("repairs") or [])})
            self._step_span = None

    def export_telemetry(self) -> str:
        """trace.json is written on every save; the OTLP export (OTEL_EXPORTER_OTLP_ENDPOINT) happens once, at exit."""
        if not self._exported:
            self._exported = self.tracer.export()
            self.record["telemetry"] = {"trace": "evidence/trace.json", "export": self._exported}
        return self._exported

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
    def _postchange_target(self) -> Path | None:
        """What a baselined gate skill lints after the change: the same file universe as the baseline (`git archive`
        of the base commit) with the code step's changed files laid over it from the checkout. Linting the working
        copy instead also reads untracked leftovers the baseline never saw — found on a real repo where a stale
        `.next.dead317/` build folder gave 62 'new high' findings the builder never touched. None when there is no
        exported baseline (no git, greenfield, --no-baseline): the checkout is linted as before."""
        base_export = self.out / "baseline-repo"
        if self.baseline.get("status") != "captured" or not base_export.is_dir():
            return None
        records = sorted(self.evidence.rglob("files-changed.json"))
        changed = read_json(records[-1]).get("files", []) if records else []
        dest = self.out / "postchange-repo"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(base_export, dest, symlinks=True)
        for rel in changed:
            if not rel or rel.startswith("/") or ".." in Path(rel).parts:
                continue
            src, out = self.repo / rel, dest / rel
            if src.is_file():
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, out)
            elif out.exists():
                out.unlink()                       # deleted by the change
        return dest

    def step_skill(self, step: dict, sdir: Path, rec: dict) -> None:
        argv = [sys.executable, "-I", str(HERE / "run_skill.py"), step["skill"], "--out", str(sdir),
                "--provider", self.args.provider]
        given = {}
        post = self._postchange_target() if step.get("skill") in BASELINE_SKILLS and "target" in (step.get("inputs") or {}) else None
        if post is not None:
            rec["target_source"] = "base commit + the code step's changed files (same file set as the baseline)"
        for k, v in (step.get("inputs") or {}).items():
            if k == "target" and post is not None:
                given[k] = str(post)
                argv += ["--input", f"target={post}"]
                continue
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
        if r.returncode == 1 and step.get("gate") and fcsv.is_file() and self.apply_waivers(step, fcsv, sdir, rec):
            return                               # every finding that failed the gate is waived, with a reason and an owner
        if r.returncode == 1 and step.get("gate"):
            why = (new_high_detail(rec["new_high_count"], rec["new_high"]) if rec.get("new_high_count")
                   else "; ".join(rec.get("failed_checks") or ["see report"]))
            raise StepError(f"gate step {step['skill']} said no (exit 1): {why}"[:GATE_DETAIL_LIMIT])

    def load_waivers(self) -> tuple[list[dict], list[str]]:
        """docs/HARNESS.md layer 8: --waivers FILE, else <repo>/.factory/waivers.json. A waiver needs rule, file,
        reason and by; an expired or incomplete one is refused (and listed)."""
        path = Path(self.args.waivers) if getattr(self.args, "waivers", None) else (self.repo / ".factory" / "waivers.json" if self.repo else None)
        if not path or not path.is_file():
            return [], []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return [], [f"{path}: not JSON ({e})"]
        items = raw.get("waivers", raw) if isinstance(raw, dict) else raw
        ok, refused, today = [], [], time.strftime("%Y-%m-%d")
        for w in items if isinstance(items, list) else []:
            missing = [k for k in ("rule", "file", "reason", "by") if not str((w or {}).get(k) or "").strip()]
            if missing:
                refused.append(f"{w}: missing {', '.join(missing)}")
            elif w.get("expires") and str(w["expires"]) < today:
                refused.append(f"{w.get('rule')} {w.get('file')}: expired {w['expires']}")
            else:
                ok.append(w)
        return ok, refused

    def apply_waivers(self, step: dict, fcsv: Path, sdir: Path, rec: dict) -> bool:
        """A gate skill said no. True when every finding that can fail it (new high/critical) is covered by a valid
        waiver: the step then passes as WAIVED and waived.csv records each finding with its reason and owner.
        Critical findings are never waivable. Found on greenfield G3 and CAPE R1: two lexical false positives
        hard-stopped whole runs with no way to dispute them except editing the skill."""
        waivers, refused = self.load_waivers()
        if refused:
            rec["waivers_refused"] = refused[:10]
        if not waivers:
            return False
        rows = [row for row in csv.DictReader(io.StringIO(fcsv.read_text(encoding="utf-8-sig")))
                if (row.get("rule") or "").strip() and not (row.get("rule") or "").startswith("#")]
        blocking = [row for row in rows if (row.get("severity") or "").lower() in ("high", "critical") and (row.get("status") or "new") != "known"]
        if not blocking or any((row.get("severity") or "").lower() == "critical" for row in blocking):
            return False
        def match(row: dict) -> dict | None:
            for w in waivers:
                if w["rule"] == row.get("rule") and w["file"] == row.get("file") and \
                        (not str(w.get("line") or "").strip() or str(w.get("line")) == str(row.get("line"))):
                    return w
            return None
        pairs = [(row, match(row)) for row in blocking]
        if any(w is None for _, w in pairs):
            rec["waived_partial"] = sum(w is not None for _, w in pairs)
            return False
        with open(sdir / "waived.csv", "w", encoding="utf-8", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["rule", "severity", "file", "line", "reason", "by", "expires"])
            for row, w in pairs:
                wr.writerow([row.get("rule"), row.get("severity"), row.get("file"), row.get("line"), w["reason"], w["by"], w.get("expires", "")])
        rec["waived"] = [f"{row.get('rule')} {row.get('file')}:{row.get('line')} — {w['reason']} (by {w['by']})" for row, w in pairs][:10]
        rec["skill_exit"], rec["exit"] = rec.get("exit"), 0     # the skill said no; the waivers answer every finding it named
        return True

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
        if ap is not None:
            ap = {"source": "file", **ap}            # --approvals / <out>/approvals.json; `approve --source mcp` says mcp
        if self.args.approve_all and ap is None:
            ap = {"by": "--approve-all", "note": "approved on the command line", "source": "cli"}
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
        rec.update(status="approved", approved_by=str(ap.get("by", "")), at=now(), exit=0, approval_source=str(ap.get("source") or "file"))
        write_json(sdir / "approval.json", {"step": step["id"], "role": step.get("role", ""), "status": "approved",
                                            "by": str(ap.get("by", "")), "note": str(ap.get("note", "")), "at": rec["at"],
                                            "source": rec["approval_source"]})
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
                return {"by": str(a.get("approved_by", "")), "note": str(a.get("note", "")), "portal_approval_id": a.get("id", ""), "source": "portal"}
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
        if step.get("kind") == "agent" and not (step.get("produces") or []):   # the code step: show it the gates up front
            rules = gate_rules_section(self.spec)
            head, sep, tail = packet.rpartition("\n## When done")
            packet = (head + rules + sep + tail) if sep else packet + rules   # before "When done": the packet ends with the resume command
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

    def honesty_row(self) -> str:
        """What this run did NOT prove, stated where nobody can miss it (found: a dry run with --approve-all read as
        "7 stages passed" though no person approved anything, no PR was opened and no CI ran)."""
        notes = []
        if self.args.dry:
            notes.append("DRY RUN on a copy: no pull request, no CI, nothing deployed")
        if self.args.approve_all:
            notes.append("every approval AUTO-APPROVED (--approve-all): no person reviewed the requirements or the plan")
        repairs = sum(len(st.get("repairs") or []) for s in self.record.get("stages", []) for st in s.get("steps", []))
        if repairs:
            notes.append(f"the builder needed {repairs} repair turn(s) after failing tests")
        sb = (self.record.get("sandbox") or {}).get("summary")
        notes.append(sb or "NOT SANDBOXED: project code ran on the host")
        llm = self.record.get("llm") or {}
        budget = getattr(self.args, "budget_usd", None)
        if llm.get("calls"):
            notes.append(f"model spend ${llm['cost_usd']:.2f} across {llm['calls']} call(s)"
                         + (f" of a ${float(budget):.2f} budget" if budget is not None else " (no --budget-usd cap)"))
        model = self.args.model or ("Claude Code's default model" if self.args.builder == "claude-code" else None)
        if model:
            notes.append(f"builder model: {model}")
        return ("**What this run does not prove:** " + "; ".join(notes) + ".") if notes else ""

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
    def real_builder(self) -> bool:
        """Claude Code writes the code: then even a dry run installs and runs the project's tests on its isolated copy —
        found on the CAPE greenfield run, where a dry run reported every stage passed while one of the app's own tests
        failed. openai-compat keeps its own --repair-cmd path; manual/none in --dry (fixtures, CI) keep skipping."""
        return getattr(self.args, "builder", "none") == "claude-code"

    def resolve_install(self, target: Path) -> tuple[str | None, str]:
        """(command, reason-when-none) for --install auto|none|<cmd>. `auto` reads the stack profile (install_cmd);
        a dry run installs nothing (the copy is throwaway and offline-reproducible)."""
        given = (getattr(self.args, "install", "auto") or "auto").strip()
        if given.lower() in ("none", "off"):
            return None, "--install none"
        if given != "auto":
            return given, ""
        if self.args.dry and not self.real_builder():
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
        if self.args.dry and not self.real_builder():
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

    @property
    def sandbox(self) -> "sbx.Sandbox":
        """docs/HARNESS.md layer 3: where project code runs (--sandbox docker|none)."""
        if getattr(self, "_sandbox", None) is None:
            a = self.args
            self._sandbox = sbx.Sandbox(getattr(a, "sandbox", "none") or "none", getattr(a, "sandbox_image", "hostroot") or "hostroot",
                                        getattr(a, "sandbox_cpus", "2") or "2", getattr(a, "sandbox_memory", "4g") or "4g")
            os.environ.update(self._sandbox.env_vars())          # child processes (the reviewer's sandbox exec) get the same box
            if not hasattr(self, "record"):
                self.record = {}
            self.record["sandbox"] = {"mode": self._sandbox.mode, "image": self._sandbox.image, "cpus": self._sandbox.cpus,
                                      "memory": self._sandbox.memory, "summary": self._sandbox.describe()}
        return self._sandbox

    def _sh(self, cmd: str, cwd: Path, timeout_s: float, network: str = "none") -> tuple[int, str]:
        """Project code (install, tests, benchmark): in the sandbox when one is configured. Only the install gets a
        network (the package registry); tests and benchmarks run with none."""
        env = {"CI": os.environ.get("CI") or "1"}   # watch-mode runners (vitest, jest) run once under CI
        try:
            argv, full_env = self.sandbox.wrap(cmd, cwd, writable=[cwd], network=network, env=env)
        except sbx.SandboxError as e:
            raise StepError(str(e)) from None
        try:
            r = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s, env=full_env)
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired as e:
            sbx.kill(argv)
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
        code, output = self._sh(cmd, target, INSTALL_TIMEOUT_S, network="host")   # the registry only
        (sdir / INSTALL_LOG).write_text(output, encoding="utf-8")
        info = {"cmd": cmd, "exit": code, "duration_s": round(time.time() - t0, 3), "log": INSTALL_LOG,
                "manifest_sha": manifest_sha(target)}
        if excluded:
            info["excluded_from_git"] = excluded
        write_json(sdir / INSTALL_JSON, info)
        rec["install"] = info
        if code != 0:
            raise StepError(f"install failed: `{cmd}` exit {code} (see {INSTALL_LOG}); tail: {output_tail(output, TEST_TAIL_IN_ERROR)!r}")

    def reinstall_if_manifest_changed(self, target: Path, sdir: Path, rec: dict) -> None:
        """The code step may add dependencies (package.json, requirements…): install again before the tests when the
        manifests changed since the install. Found on the CAPE sync spike: the builder added `pg`, the install had run
        before the code landed, and 7 test files failed with "Failed to load url pg" through three repair turns."""
        prev = read_json(sdir / INSTALL_JSON) if (sdir / INSTALL_JSON).is_file() else {}
        if prev.get("exit") != 0 or not prev.get("cmd") or prev.get("manifest_sha") == manifest_sha(target):
            return
        cmd = str(prev["cmd"])
        if cmd.startswith("npm ci"):
            cmd = "npm install --no-audit --no-fund"     # the lockfile is behind package.json: ci would refuse
        t0 = time.time()
        code, output = self._sh(cmd, target, INSTALL_TIMEOUT_S, network="host")   # the registry only
        (sdir / "reinstall.log").write_text(output, encoding="utf-8")
        info = {**prev, "reinstall": {"cmd": cmd, "exit": code, "duration_s": round(time.time() - t0, 3), "log": "reinstall.log"},
                "manifest_sha": manifest_sha(target)}
        write_json(sdir / INSTALL_JSON, info)
        rec["install"] = info
        if code != 0:
            raise StepError(f"reinstall after a dependency change failed: `{cmd}` exit {code}; tail: {output_tail(output, TEST_TAIL_IN_ERROR)!r}")

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
        self.reinstall_if_manifest_changed(target, sdir, rec)
        t0 = time.time()
        code, output = self._sh(cmd, target, TEST_TIMEOUT_S)
        (sdir / TESTS_LOG).write_text(output, encoding="utf-8")
        info = {"cmd": cmd, "exit": code, "duration_s": round(time.time() - t0, 3), "summary": test_summary(output),
                "tail": output_tail(output, TEST_TAIL), "log": TESTS_LOG}
        stubs = self.unfilled_test_stubs(target)
        if stubs:
            info["unfilled_stubs"] = stubs
        self.record_tests(sdir, rec, info)
        if code != 0:
            raise StepError(f"tests failed: `{cmd}` exit {code}" + (f" ({info['summary']})" if info["summary"] else "")
                            + f"; tail: {output_tail(output, TEST_TAIL_IN_ERROR)!r}")
        # found on greenfield G2: "56 passed, 11 skipped" passed the gate with 11 scaffold files still all todo. A model
        # builder is sent back to fill them (repair turn); a hand-supplied diff (--builder manual) keeps them listed in
        # tests.json and on the evidence Tests line, where the reviewer of that diff sees them
        if stubs and getattr(self.args, "builder", "") in ("claude-code", "openai-compat"):
            raise StepError(f"tests: {len(stubs)} test file(s) scaffolded by test-strategy-tdd still hold only todo stubs, so the "
                            f"acceptance criteria they name are untested: {', '.join(stubs[:8])}. Replace each todo with a real "
                            "test of that criterion (or move the criterion's real test into that file and delete the stub file)")

    @staticmethod
    def unfilled_test_stubs(target: Path) -> list[str]:
        """Test files test-strategy-tdd scaffolded (its "Red first: generated by test-strategy-tdd" header) that still
        contain `.todo(` / `.fixme(` — criteria nobody tested. A file whose todos were all replaced does not count."""
        out = []
        for d in ("tests", "e2e", "__tests__"):
            base = target / d
            if base.is_dir():
                for f in sorted(base.rglob("*")):
                    if f.is_file() and f.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs") and "node_modules" not in f.parts:
                        txt = f.read_text(encoding="utf-8", errors="replace")
                        if "generated by test-strategy-tdd" in txt and re.search(r"\b(it|test)\.(todo|fixme)\(", txt):
                            out.append(f.relative_to(target).as_posix())
        return out

    @staticmethod
    def visual_routes(target: Path) -> list[str]:
        """The pages a person would open: Next.js app/ (or src/app/) page files without dynamic segments, / first."""
        routes = []
        for base in (target / "app", target / "src" / "app"):
            if base.is_dir():
                for page in sorted(base.rglob("page.*")):
                    if page.suffix not in (".tsx", ".jsx", ".ts", ".js") or "node_modules" in page.parts:
                        continue
                    parts = [x for x in page.parent.relative_to(base).parts if not (x.startswith("(") or x.startswith("@"))]
                    if any(x.startswith("[") or x.startswith("_") for x in parts):
                        continue
                    routes.append("/" + "/".join(parts))
        routes = sorted(set(routes), key=lambda r: (r != "/", r.count("/"), r))
        return routes[:VISUAL_MAX_ROUTES] or ["/"]

    def run_visual(self, target: Path, sdir: Path, rec: dict) -> None:
        """After the tests pass: scripts/visual_check.py starts the app and looks at every page at desktop and phone
        width. Found on the CAPE greenfield run: 85/85 tests and every gate passed on a page with no styling at all.
        A failure is a StepError (so a claude-code builder gets a repair turn); no web UI is recorded as not
        applicable, never as a pass; --visual off records that it was switched off."""
        if getattr(self.args, "visual", "auto") == "off":
            rec["visual"] = {"verdict": "off", "detail": "switched off with --visual off"}
            return
        out = sdir / VISUAL_DIR
        cmd = [sys.executable, str(HERE / "visual_check.py"), "--target", str(target), "--out", str(out)]
        for r in self.visual_routes(target):
            cmd += ["--route", r]
        if self.sandbox.mode != "none":   # the app AND the browser run in the box (network none, loopback only)
            cmd = ["python3", "-I", *cmd[1:]]
            try:
                argv, venv = self.sandbox.wrap(shlex.join(cmd), target, writable=[target, out], readonly=[HERE])
            except sbx.SandboxError as e:
                raise StepError(str(e)) from None
        else:
            argv, venv = cmd, None
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=VISUAL_TIMEOUT_S, env=venv)
        except subprocess.TimeoutExpired:
            sbx.kill(argv)
            rec["visual"] = {"verdict": "fail", "detail": f"the visual check did not finish in {VISUAL_TIMEOUT_S} s"}
            raise StepError(rec["visual"]["detail"])
        res = read_json(out / "visual.json") if (out / "visual.json").is_file() else {}
        verdict = res.get("verdict") or ("error" if r.returncode == 2 else "fail")
        rec["visual"] = {"verdict": verdict, "routes": res.get("routes"), "start_cmd": res.get("start_cmd"), "reason": res.get("start_reason"),
                         "failures": (res.get("failures") or [])[:12], "warnings": (res.get("warnings") or [])[:6],
                         "screenshots": [f"{VISUAL_DIR}/{x}" for x in res.get("screenshots") or []],
                         "detail": (r.stdout.strip() or r.stderr.strip())[-400:]}
        if verdict in ("fail", "error"):
            raise StepError("visual check failed: " + "; ".join(rec["visual"]["failures"][:6] or [rec["visual"]["detail"]])
                            + f" — screenshots in {out}")

    def run_bench(self, target: Path, sdir: Path, rec: dict) -> bool:
        """After the tests pass: `npm run bench` when package.json defines it. Found on the CAPE 2.0 chain (R1): the
        brief asked for p50/p95/p99 and the builder, which has no shell, honestly wrote "not yet measured" — nothing in
        the pipeline ever ran it. The output goes to <step>/bench.log, the record to bench.json and run.json `bench`;
        a non-zero exit fails the step (a repair turn for claude-code). Returns True when a benchmark ran."""
        pkg = target / "package.json"
        try:
            scripts = (json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}) if pkg.is_file() else {}
        except json.JSONDecodeError:
            scripts = {}
        if "bench" not in scripts:
            rec["bench"] = {"skipped": "package.json defines no bench script"}
            return False
        t0 = time.time()
        code, output = self._sh("npm run bench", target, BENCH_TIMEOUT_S)
        (sdir / BENCH_LOG).write_text(output, encoding="utf-8")
        info = {"cmd": "npm run bench", "exit": code, "duration_s": round(time.time() - t0, 3), "tail": output_tail(output, TEST_TAIL),
                "log": BENCH_LOG}
        write_json(sdir / "bench.json", info)
        rec["bench"] = {k: v for k, v in info.items() if k != "tail"}
        if code != 0:
            raise StepError(f"benchmark failed: `npm run bench` exit {code}; tail: {output_tail(output, TEST_TAIL_IN_ERROR)!r}")
        return True

    def acceptance_sources(self, target: Path) -> list[tuple[str, Path]]:
        """What the reviewer judges against: the goal document (--goal, or docs/*GOAL*.md in the repo), the brief, the
        product manager's PRD (acceptance criteria) and the architect's plan (per-task acceptance)."""
        out: list[tuple[str, Path]] = []
        goal = getattr(self.args, "goal", None)
        if goal and Path(goal).is_file():
            out.append(("goal document", Path(goal)))
        else:
            for g in sorted((target / "docs").glob("*GOAL*.md")) if (target / "docs").is_dir() else []:
                out.append(("goal document", g))
        if self.inputs.get("brief") and Path(str(self.inputs["brief"])).is_file():
            out.append(("brief (goals and constraints for THIS change)", Path(str(self.inputs["brief"]))))
        for sid, name, label in (("prd-refine", PRD_MD, "PRD with acceptance criteria"), ("plan-refine", TASKS_CSV, "plan tasks with acceptance"),
                                 ("plan-refine", PLAN_MD, "plan")):
            d = self.step_dirs.get(sid)
            if d and (d / name).is_file():
                out.append((label, d / name))
        return out

    def run_acceptance(self, target: Path, sdir: Path, rec: dict) -> None:
        """docs/HARNESS.md layer 1 — the requirements verification gate. Found on the CAPE 2.0 chain: 486 tests and
        every gate passed while the goal's one non-negotiable (no stale data) was NOT met; an independent reviewer
        found it in 4 minutes. A fresh claude session (never the builder's summary) reviews a disposable copy of the
        code against the acceptance sources, may run commands only through the sandbox, and must give every criterion
        a verdict with evidence it produced. NOT_MET, PARTLY on a must-have, or a critical/high defect fails the
        step (the findings become the builder's repair turn); a reviewer that produces no valid result is a
        ReviewerError (never charged to the builder)."""
        mode = getattr(self.args, "acceptance", "auto") or "auto"
        if mode == "off" or (mode == "auto" and self.args.builder not in ("claude-code", "openai-compat")):
            rec["acceptance"] = {"verdict": "not_run", "detail": "switched off (--acceptance off)" if mode == "off"
                                 else f"--acceptance auto runs for model builders; the {self.args.builder} builder's diff was not reviewed"}
            return
        exe = shutil.which("claude")
        if not exe:
            rec["acceptance"] = {"verdict": "not_run", "detail": "`claude` is not on PATH: no reviewer available"}
            return
        sources = self.acceptance_sources(target)
        if not sources:
            rec["acceptance"] = {"verdict": "not_run", "detail": "no acceptance criteria found (no goal document, brief, PRD or plan)"}
            return
        adir = sdir / ACCEPT_DIR
        round_no = len(rec.get("acceptance_rounds") or []) + 1
        copy = adir / f"review-copy-{round_no}"
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(target, copy, ignore=shutil.ignore_patterns("node_modules", ".next", ".git", "coverage"), symlinks=True)
        if (target / "node_modules").is_dir():
            (copy / "node_modules").symlink_to((target / "node_modules").resolve())
        result = adir / f"round-{round_no}-{ACCEPT_JSON}"
        result.unlink(missing_ok=True)
        sb = f"python3 {HERE / 'sandbox.py'} exec --dir {copy}"
        crit = "\n".join(f"- {label}: {path}" for label, path in sources)
        prompt = (
            f"Review the application in the current folder ({copy}) against these acceptance sources (read every one first):\n{crit}\n\n"
            f"Run any command ONLY as `{sb} -- <command>` (e.g. `{sb} -- npx vitest run tests/x.test.ts`); it runs in the "
            f"project's sandbox ({self.sandbox.describe()}). DATABASE_URL, if the tests need one, is already set. You may write "
            f"experiment files (e.g. tests/zz-acceptance/*.test.ts) in this folder: it is a disposable copy.\n\n"
            f"Write {result} as JSON: {{\"criteria\": [{{\"id\": \"C1\", \"source\": \"which document and section\", \"text\": \"the criterion\", "
            f"\"must\": true, \"verdict\": \"MET|PARTLY|NOT_MET|UNVERIFIED\", \"evidence\": \"what you ran or read (file:line, command and its result)\"}}], "
            f"\"defects\": [{{\"severity\": \"critical|high|medium|low\", \"title\": \"...\", \"location\": \"file:line\", \"confirmed_by\": \"how\"}}], "
            f"\"summary\": \"three sentences\"}}.\n"
            "Rules: one criterion per testable requirement of THIS change (the brief and PRD; use the goal document for the "
            "non-negotiables this change touches); must=true for requirements the sources state as mandatory. For every must "
            "criterion about behaviour, write and RUN an experiment that would fail if the criterion were not met, and cite the "
            "command and its result; reading code is not enough. Hunt end to end for violations of the goal's non-negotiables "
            "(drive the real services: e.g. change data the way the outside world would, then follow it through every path the "
            "learner or the system takes) and check that tests named for a behaviour would fail without it. MET needs evidence "
            "you produced; anything you could not verify is UNVERIFIED, never MET. A defect needs a concrete confirmation (a "
            "failing experiment or a reasoned scenario through named code). Do not change files outside this folder and never "
            "edit the application to make it pass.")
        (adir / f"round-{round_no}-prompt.txt").write_text(prompt, encoding="utf-8")
        model = ["--model", self.args.review_model] if getattr(self.args, "review_model", None) else \
                (["--model", self.args.model] if getattr(self.args, "model", None) else [])
        cmd = [exe, *model, "--permission-mode", "acceptEdits", "--add-dir", str(adir.resolve()),
               *[x for _, pth in sources for x in ("--add-dir", str(pth.parent.resolve()))],
               "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "LS", f"Bash({sb}:*)",
               "--append-system-prompt", REVIEWER_RULES, "-p", prompt, "--output-format", "json"]
        cmdlog = adir / f"round-{round_no}-commands.jsonl"
        cmdlog.unlink(missing_ok=True)
        os.environ["SF_SANDBOX_LOG"] = str(cmdlog)     # sandbox.py exec appends every command the reviewer runs
        try:
            r = self.run_claude(cmd, copy, ACCEPT_TIMEOUT_S, f"acceptance review {round_no}")
            ran = cmdlog.read_text(encoding="utf-8").splitlines() if cmdlog.is_file() else []
            if not ran and result.is_file():
                # a review that only read code missed the CAPE R3 critical defect (stale data committed): one more turn
                nudge = (f"You wrote {result.name} without running a single experiment. Reading code is not enough: run the "
                         f"experiments the rules ask for through `{sb} -- <command>`, then rewrite {result} with what they showed.")
                cmd2 = cmd[:cmd.index("-p") + 1] + [prompt + "\n\n" + nudge] + cmd[cmd.index("-p") + 2:]
                r = self.run_claude(cmd2, copy, ACCEPT_TIMEOUT_S, f"acceptance review {round_no} (experiments)")
                ran = cmdlog.read_text(encoding="utf-8").splitlines() if cmdlog.is_file() else []
        finally:
            os.environ.pop("SF_SANDBOX_LOG", None)
        (adir / f"round-{round_no}-reply.txt").write_text((r.stdout or "") + "\n--- stderr ---\n" + (r.stderr or ""), encoding="utf-8")
        if not ran:
            raise ReviewerError(f"acceptance reviewer ran no experiment in the sandbox (round {round_no}): a review from reading "
                                f"alone is not accepted")
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
            crits = [c for c in data.get("criteria") or [] if isinstance(c, dict)]
            if not crits:
                raise ValueError("no criteria")
        except (OSError, ValueError, json.JSONDecodeError) as e:
            raise ReviewerError(f"acceptance reviewer produced no valid {result.name} ({e}); exit {r.returncode}") from None
        for c in crits:
            v = str(c.get("verdict", "")).upper().replace(" ", "_")
            c["verdict"] = v if v in VERDICTS else "UNVERIFIED"
            if c["verdict"] == "MET" and not str(c.get("evidence") or "").strip():
                c["verdict"], c["downgraded"] = "UNVERIFIED", "MET without evidence"
        defects = [x for x in data.get("defects") or [] if isinstance(x, dict)]
        blocking = [c for c in crits if c["verdict"] == "NOT_MET" or (c["verdict"] == "PARTLY" and c.get("must"))]
        severe = [x for x in defects if str(x.get("severity", "")).lower() in ("critical", "high")]
        counts = {v: sum(c["verdict"] == v for c in crits) for v in VERDICTS}
        verdict = "fail" if (blocking or severe) else "pass"
        summary = {"round": round_no, "verdict": verdict, "counts": counts, "defects": len(defects), "severe": len(severe), "experiments": len(ran),
                   "file": str(result.relative_to(sdir))}
        rec.setdefault("acceptance_rounds", []).append(summary)
        write_json(sdir / ACCEPT_JSON, {"criteria": crits, "defects": defects, "summary": data.get("summary", ""), "round": round_no,
                                        "verdict": verdict, "sources": [{"label": l, "path": str(p_)} for l, p_ in sources]})
        lines = [f"# Acceptance review — round {round_no}: {verdict.upper()}", "",
                 "Independent reviewer (a fresh model session that never saw the builder's notes); every MET carries evidence it produced; "
                 f"{len(ran)} experiment command(s) run in the sandbox (round-{round_no}-commands.jsonl).", "",
                 f"MET {counts['MET']} · PARTLY {counts['PARTLY']} · NOT MET {counts['NOT_MET']} · UNVERIFIED {counts['UNVERIFIED']} · "
                 f"defects {len(defects)} ({len(severe)} critical/high)", "", "| ID | Must | Verdict | Criterion | Evidence |", "|---|---|---|---|---|"]
        lines += [f"| {c.get('id', '')} | {'yes' if c.get('must') else ''} | {c['verdict']} | {str(c.get('text', '')).replace('|', '¦')[:200]} | "
                  f"{str(c.get('evidence', '')).replace('|', '¦')[:300]} |" for c in crits]
        if defects:
            lines += ["", "| Severity | Defect | Location | Confirmed by |", "|---|---|---|---|"]
            lines += [f"| {x.get('severity', '')} | {str(x.get('title', '')).replace('|', '¦')[:160]} | {x.get('location', '')} | "
                      f"{str(x.get('confirmed_by', '')).replace('|', '¦')[:200]} |" for x in defects]
        lines += ["", f"Summary: {data.get('summary', '')}"]
        (sdir / ACCEPT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")
        rec["acceptance"] = {"verdict": verdict, "counts": counts, "defects": len(defects), "severe": len(severe), "md": ACCEPT_MD, "experiments": len(ran),
                             "rounds": round_no}
        if verdict == "fail":
            items = [f"{c.get('id')} {c['verdict']}: {c.get('text', '')} — {c.get('evidence', '')}"[:400] for c in blocking[:8]]
            items += [f"{x.get('severity')} defect: {x.get('title')} at {x.get('location')} — {x.get('confirmed_by')}"[:400] for x in severe[:6]]
            raise StepError("acceptance review failed: " + " | ".join(items) + f" — full review in {sdir / ACCEPT_MD}")

    def verify(self, cmd: str | None, reason: str, target: Path, sdir: Path, rec: dict) -> None:
        """What judges the builder's code: the project's tests, then (when they pass) its benchmark, then a look at
        the running app."""
        self.run_tests(cmd, reason, target, sdir, rec)
        self.run_bench(target, sdir, rec)
        self.run_visual(target, sdir, rec)
        self.run_acceptance(target, sdir, rec)

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
            r = self.run_claude(self.claude_cmd(exe, prompt), target, 1800, step["id"])
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
                     "existing directory with the repository's language and framework conventions (same extension as its neighbours). "
                     f"These stack-convention directories may be created when absent: {', '.join(sorted(CONVENTION_DIRS))}/.")
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
                    if "/" in f and not (target / top).is_dir() and top not in CONVENTION_DIRS:
                        problems.append(f"{r.get('id') or '?'}: {f} is under {top}/, which does not exist in the repository (invented layout)")
        return problems

    def claude_cmd(self, exe: str, prompt: str) -> list[str]:
        """`claude -p` for a builder step. Non-interactive runs cannot ask for permission, so without these flags every
        file write is silently refused and the step fails with "did not write" (found running feature-delivery with
        --builder claude-code): edits are accepted, and the run directory is added so a step that produces evidence
        files (prd-final.md, plan.md, tasks.csv, files.txt) can write them outside the checkout."""
        # No shell: a non-interactive run cannot approve one, and a model that reaches for a helper script then stops to
        # ask (seen live at plan-refine: "the shell keeps asking for approval … tell me whether to approve"). The file
        # tools are allowed outright and the run is told so; the executor itself runs installs and tests.
        model = ["--model", self.args.model] if getattr(self.args, "model", None) else []
        return [exe, *model, "--permission-mode", "acceptEdits", "--add-dir", str(self.out.resolve()),
                "--allowedTools", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "LS",
                "--disallowedTools", "Bash",
                "--append-system-prompt", NONINTERACTIVE_RULES, "-p", prompt, "--output-format", "json"]

    def run_claude(self, cmd: list[str], cwd: Path, timeout: float, label: str) -> subprocess.CompletedProcess:
        """Every model call goes through here (budget circuit breaker + telemetry, docs/HARNESS.md layers 4 and 5).
        The call runs with --output-format json; its cost, tokens, turns and duration are recorded on the current
        step span and in run.json `llm` totals. With --budget-usd the call gets --max-budget-usd = what the run has
        left; a run already over budget does not start the call. Returns a CompletedProcess whose stdout is the
        model's reply text (what callers used before), so every caller keeps working."""
        budget = getattr(self.args, "budget_usd", None)
        spent = float((self.record.get("llm") or {}).get("cost_usd") or 0)
        if budget is not None:
            left = round(float(budget) - spent, 4)
            if left <= 0:
                raise StepError(f"budget exceeded: this run has spent ${spent:.2f} of its ${float(budget):.2f} budget "
                                f"(--budget-usd); {label} was not started")
            cmd = [cmd[0], "--max-budget-usd", f"{left:.4f}", *cmd[1:]]
        t0 = time.time_ns()
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        meta: dict = {}
        try:
            meta = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
        except json.JSONDecodeError:
            meta = {}
        usage = meta.get("usage") or {}
        cost = float(meta.get("total_cost_usd") or 0)
        tok_in = int(usage.get("input_tokens") or 0) + int(usage.get("cache_creation_input_tokens") or 0) + int(usage.get("cache_read_input_tokens") or 0)
        tok_out = int(usage.get("output_tokens") or 0)
        tot = self.record.setdefault("llm", {"calls": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0})
        tot["calls"] += 1
        tot["cost_usd"] = round(tot["cost_usd"] + cost, 4)
        tot["input_tokens"] += tok_in
        tot["output_tokens"] += tok_out
        self.tracer.record(f"llm {label}", t0, time.time_ns(), parent=getattr(self, "_step_span", None),
                           **{"llm.call": True, "llm.label": label, "llm.model": getattr(self.args, "model", None) or "claude-code default",
                              "llm.cost_usd": cost, "llm.input_tokens": tok_in, "llm.output_tokens": tok_out,
                              "llm.turns": int(meta.get("num_turns") or 0), "llm.exit": r.returncode,
                              "llm.subtype": str(meta.get("subtype") or "")})
        sub = str(meta.get("subtype") or "")
        if "budget" in sub:
            raise StepError(f"budget exceeded during {label}: the model stopped at the --budget-usd limit "
                            f"(run total now ${tot['cost_usd']:.2f} of ${float(budget or 0):.2f})")
        text = str(meta.get("result") or "") if meta else r.stdout
        return subprocess.CompletedProcess(cmd, r.returncode if not meta.get("is_error") else (r.returncode or 1), text, r.stderr)

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
        if builder == "claude-code":
            # the product manager is Claude Code on the person's own subscription (no API key): it reads the packet and
            # writes prd-final.md at the expected path; the requirements gate then judges it like any other PRD
            exe = shutil.which("claude")
            if not exe:
                raise StepError("builder claude-code: `claude` is not on PATH (install Claude Code, or use --builder manual with --prd <file>)")
            rec["status"] = "ok"
            prompt = self.write_packet(step, sdir, need, packet_inputs, PACKET_SKILLS[PRD_MD])
            (sdir / "prompt.txt").write_text(prompt, encoding="utf-8")
            target = self.repo if self.repo and self.repo.is_dir() else self.out   # reads the checkout, writes only the PRD
            t0 = time.time()
            r = self.run_claude(self.claude_cmd(exe, prompt), target, 1800, step["id"])
            rec["agent_exit"], rec["agent_duration_s"] = r.returncode, round(time.time() - t0, 3)
            (sdir / "agent-stderr.txt").write_text(r.stderr, encoding="utf-8")
            (sdir / "agent-stdout.txt").write_text(r.stdout, encoding="utf-8")
            if r.returncode != 0:
                raise StepError(f"claude -p exited {r.returncode}: {r.stderr.strip().splitlines()[-1:] or ''}"[:300])
            if not expected.is_file():
                raise StepError(f"builder claude-code did not write {expected}")
            rec.update(exit=0, prd_source="claude-code")
            write_json(sdir / "prd-refine.json", {"source": "claude-code", "skipped": False, "draft": draft,
                                                  "note": f"written by claude -p in {rec['agent_duration_s']}s"})
            return True
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
            r = self.run_claude(self.claude_cmd(exe, prompt), target, 1800, step["id"])
            rec["agent_exit"], rec["agent_duration_s"] = r.returncode, round(time.time() - t0, 3)
            (sdir / "agent-stderr.txt").write_text(r.stderr, encoding="utf-8")
            (sdir / "agent-stdout.txt").write_text(r.stdout, encoding="utf-8")
            if r.returncode != 0:
                raise StepError(f"claude -p exited {r.returncode}: {r.stderr.strip().splitlines()[-1:] or ''}"[:300])
            absent = [f for f in PLAN_FILES if not expected[f].is_file()]
            if absent:
                raise StepError(f"builder claude-code did not write {', '.join(str(expected[f]) for f in absent)}")
            # one repair turn when the plan names files that do not fit the checkout (the openai-compat builder has had
            # this through extra_check); found on greenfield G1/G3: a single refusal ended the whole run
            misfit = self.plan_fits_repo(str(expected[TASKS_CSV]), target, self.record.get("stack_profile") or self.profile or {})
            if misfit:
                ask = (f"The plan you wrote at {expected[TASKS_CSV]} names files that do not fit this repository:\n"
                       + "\n".join(f"- {m}" for m in misfit[:12])
                       + f"\n\nRewrite {expected[TASKS_CSV]} (and {expected[PLAN_MD]} where it names the same files) so every file "
                         "is an existing file, a new file in an existing directory, or a new file in one of the stack-convention "
                         "directories listed in the repository layout. Change nothing else and do not touch the repository.")
                (sdir / "repair-1-prompt.txt").write_text(ask, encoding="utf-8")
                t1 = time.time()
                rr = self.run_claude(self.claude_cmd(exe, ask), target, 1800, f"{step['id']} repair 1")
                (sdir / "repair-1-stderr.txt").write_text(rr.stderr, encoding="utf-8")
                rec.setdefault("repairs", []).append({"turn": 1, "exit": rr.returncode, "duration_s": round(time.time() - t1, 3),
                                                      "reason": "; ".join(misfit[:4])[:300]})
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
                self.verify(*self.resolve_tests(target), target, sdir, rec)   # the tests, then a look at the running app, judge the diff
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
            r = self.run_claude(self.claude_cmd(exe, prompt), target, 3600, step["id"])
            rec["agent_exit"], rec["agent_duration_s"] = r.returncode, round(time.time() - t0, 3)
            (sdir / "agent-stderr.txt").write_text(r.stderr, encoding="utf-8")
            if r.returncode != 0:
                raise StepError(f"claude -p exited {r.returncode}: {r.stderr.strip().splitlines()[-1:] or ''}"[:300])
            def capture(summary: str) -> None:
                git(target, "add", "-A")
                _, diff = git(target, "diff", "--cached", "--binary")
                patch = sdir / "captured.patch"
                patch.write_text(diff, encoding="utf-8")
                self._record_diff(patch, sdir, rec, plan, summary, files)
                patch.unlink()

            capture(r.stdout)
            # the project's tests judge the agent's code; a failure goes back to Claude Code as a repair turn (like the
            # openai-compat builder) — found on the CAPE greenfield run: 95 of 96 tests passed and nobody was asked to
            # fix the one co-requisite failure. 1 + max(1, --rounds) turns in all; the last result stands.
            tcmd, treason = self.resolve_tests(target)
            repairs = max(1, int(getattr(self.args, "rounds", 2) or 2))
            for turn in range(repairs + 1):
                try:
                    self.verify(tcmd, treason, target, sdir, rec)
                    if (rec.get("bench") or {}).get("cmd"):
                        capture(r.stdout)                         # the results file the benchmark wrote joins the diff
                    break
                except StepError as failure:
                    if isinstance(failure, ReviewerError) or turn == repairs or \
                            (not tcmd and not str(failure).startswith(("visual check", "acceptance review"))):
                        raise
                    if str(failure).startswith("acceptance review"):
                        ask = (f"An independent reviewer checked your change against the acceptance criteria and it does not meet them. "
                               f"Read {sdir / ACCEPT_MD} (and {sdir / ACCEPT_JSON}) first. Fix the code so every NOT MET / PARTLY "
                               f"criterion is met and every critical/high defect is gone; add a test for each one that fails "
                               f"without your fix (a test that passes with the feature removed does not count). Prefer the files the "
                               f"plan names; files outside it are recorded. Keep `{tcmd}` passing. Do not weaken existing tests.\n\n"
                               f"Findings:\n{failure}")
                        (sdir / f"repair-{turn + 1}-prompt.txt").write_text(ask, encoding="utf-8")
                        t1 = time.time()
                        rr = self.run_claude(self.claude_cmd(exe, ask), target, 3600, f"{step['id']} repair {turn + 1}")
                        (sdir / f"repair-{turn + 1}-stderr.txt").write_text(rr.stderr, encoding="utf-8")
                        rec.setdefault("repairs", []).append({"turn": turn + 1, "exit": rr.returncode, "duration_s": round(time.time() - t1, 3),
                                                              "reason": str(failure)[:300]})
                        if rr.returncode != 0:
                            raise StepError(f"claude -p (repair {turn + 1}) exited {rr.returncode}: {rr.stderr.strip().splitlines()[-1:] or ''}"[:300])
                        capture(rr.stdout)
                        continue
                    what = ("The running app failed the visual check (a browser opened each page at 1440 and 390 px wide; "
                            f"screenshots and visual.json are in {sdir / VISUAL_DIR}). Fix the UI so every page is styled, "
                            "not empty, loads without errors and does not scroll sideways on a phone; keep `" + str(tcmd) + "` passing"
                            if str(failure).startswith("visual check") else f"The project's tests fail after your change. Fix the code so `{tcmd}` passes")
                    ask = (f"{what}: change only the files "
                           f"the plan allows and their tests. Do not delete or weaken a test unless it contradicts the plan's "
                           f"acceptance criteria; if one does, fix the test and say why in one line. The full test log is at "
                           f"{sdir / TESTS_LOG}.\n\nFailure:\n{failure}")
                    (sdir / f"repair-{turn + 1}-prompt.txt").write_text(ask, encoding="utf-8")
                    t1 = time.time()
                    rr = self.run_claude(self.claude_cmd(exe, ask), target, 3600, f"{step['id']} repair {turn + 1}")
                    (sdir / f"repair-{turn + 1}-stderr.txt").write_text(rr.stderr, encoding="utf-8")
                    rec.setdefault("repairs", []).append({"turn": turn + 1, "exit": rr.returncode, "duration_s": round(time.time() - t1, 3),
                                                          "reason": str(failure)[:300]})
                    if rr.returncode != 0:
                        raise StepError(f"claude -p (repair {turn + 1}) exited {rr.returncode}: {rr.stderr.strip().splitlines()[-1:] or ''}"[:300])
                    capture(rr.stdout)
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
            self.run_visual(target, sdir, rec)
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
        # The pull request through GitHub's REST API (gh api), never `gh pr create`/`gh pr view`: those use GraphQL,
        # which fine-grained tokens and some proxies refuse (found by the first real greenfield run). Idempotent: an
        # open PR for the branch is reused.
        key = github_key(self)
        if not key:
            raise StepError(f"pr step: cannot tell owner/name from the origin remote of {repo}; the pull request needs a GitHub repository")
        owner = key.split("/")[0]
        info = self._find_pr(key, owner, branch, env, repo)
        if not info:
            spec = {"title": title[:250], "head": branch, "base": self._default_branch(key, env, repo), "body": Path(body).read_text(encoding="utf-8", errors="replace")[:60000]}
            spec_path = sdir / "pr-request.json"
            write_json(spec_path, spec)
            r = subprocess.run(["gh", "api", f"repos/{key}/pulls", "--input", str(spec_path)], cwd=str(repo), capture_output=True, text=True, env=env)
            if r.returncode != 0:
                raise StepError(f"gh api repos/{key}/pulls (create PR): {(r.stderr or r.stdout).strip()[:300]}")
            try:
                data = json.loads(r.stdout)
            except ValueError:
                data = {}
            info = {"number": data.get("number"), "url": data.get("html_url"), "headRefOid": (data.get("head") or {}).get("sha")}
        url = info.get("url")
        write_json(sdir / "pr.json", {"dry": False, "branch": branch, "title": title, "number": info.get("number"),
                                      "url": url, "head_sha": info.get("headRefOid") or head.strip(),
                                      "committed_as": BOT_NAME})
        rec["exit"] = 0

    @staticmethod
    def _find_pr(key: str, owner: str, branch: str, env: dict, cwd: Path) -> dict:
        r = subprocess.run(["gh", "api", f"repos/{key}/pulls?state=open&head={owner}:{branch}", "--jq", ".[0] | {number, url: .html_url, headRefOid: .head.sha}"],
                           cwd=str(cwd), capture_output=True, text=True, env=env)
        if r.returncode == 0 and r.stdout.strip().startswith("{"):
            try:
                data = json.loads(r.stdout)
                if data.get("number"):
                    return data
            except ValueError:
                pass
        return {}

    @staticmethod
    def _default_branch(key: str, env: dict, cwd: Path) -> str:
        r = subprocess.run(["gh", "api", f"repos/{key}", "--jq", ".default_branch"], cwd=str(cwd), capture_output=True, text=True, env=env)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "main"

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
            waived = f" — WAIVED {len(s['waived'])}: " + "; ".join(s["waived"][:3]) if s.get("waived") else ""
            return ("pass" if ok else "fail"), f"step '{gate['step']}' exit {s.get('exit')}{waived}" + ("" if ok else ": " + "; ".join(s.get("failed_checks") or ["see its report"]))
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
            if self.args.dry:   # nothing outside the run happened: never report a dry run's deploy as satisfied
                return "not_run", f"dry run: no pull request was opened and CI never ran ({gate.get('what', '')} was not checked)"
            return "recorded", f"to be confirmed outside the run: {gate.get('what', '')}"
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
                self.bench_row(), "",
                self.acceptance_row(), "",
                self.visual_row(), "",
                self.honesty_row(), "",
                "| Stage | Role | Gate | Verdict | Evidence |", "|---|---|---|---|---|"]
        for s in self.record.get("stages", []):
            g = s.get("gate") or {}
            ev = ", ".join(f"[{Path(p).name}]({p})" for p in s.get("evidence_files") or []) or "—"
            verdict = {"pass": "PASS", "fail": "FAIL", "recorded": "RECORDED (not verified)", "not_run": "NOT RUN"}.get(
                g.get("verdict", ""), s.get("status", "").upper())
            auto = [st["id"] for st in s.get("steps", []) if st.get("kind") == "approval" and st.get("approved_by") == "--approve-all"]
            if auto and verdict == "PASS":
                verdict = "PASS (approval AUTO-APPROVED, no person reviewed)"
            rows.append(f"| {s['id']} | {s['role']} | {g.get('kind', '')} | {verdict} | {ev} |")
        rows += ["", "Gate detail per stage is in `<stage>/gate.json`; step logs in `<stage>/<step>/`.", ""]
        rows += self.provenance_rows()
        (self.evidence / "EVIDENCE.md").write_text("\n".join(rows), encoding="utf-8")

    # ---- provenance (docs/DELIVERY-PIPELINES.md → Local mode): what ran, at which version, approved by whom
    def provenance(self) -> dict:
        """<out>/evidence/provenance.json: every skill step with its name, version and directory sha256; the executor's
        own git sha; the pipeline name, version and file sha256; builder / provider / model; every approval and
        rejection with its source (file | portal | mcp | cli); every gate verdict with its timestamp."""
        spec_path = getattr(self, "spec_path", None)
        pipeline = {"name": self.spec.get("name", ""), "version": self.spec.get("version", ""),
                    "path": str(spec_path) if spec_path else "", "sha256": sha256(spec_path) if spec_path and Path(spec_path).is_file() else ""}
        skills, seen = [], set()
        for check, e in sorted(((self.record.get("baseline") or {}).get("checks") or {}).items()):
            if e.get("source") == "captured" and e.get("skill"):
                skills.append({"stage": BASELINE_DIR, "step": check, **skill_fingerprint(e["skill"]), "exit": e.get("exit")})
                seen.add((BASELINE_DIR, check))
        for s in self.record.get("stages", []):
            for st in s.get("steps", []):
                if st.get("kind") == "skill" and st.get("skill") and (s["id"], st["id"]) not in seen:
                    skills.append({"stage": s["id"], "step": st["id"], **skill_fingerprint(st["skill"]), "exit": st.get("exit"),
                                   "status": st.get("status")})
                    seen.add((s["id"], st["id"]))
        approvals, gates = [], []
        for s in self.record.get("stages", []):
            for st in s.get("steps", []):
                if st.get("kind") == "approval" and st.get("status") == "approved":
                    aj = self.step_dirs.get(st["id"], Path("/nonexistent")) / "approval.json"
                    a = read_json(aj) if aj.is_file() else {}
                    approvals.append({"stage": s["id"], "step": st["id"], "by": st.get("approved_by", ""), "note": a.get("note", ""),
                                      "at": st.get("at", ""), "source": st.get("approval_source") or a.get("source") or "file"})
            g = s.get("gate") or {}
            if g:
                gates.append({"stage": s["id"], "kind": g.get("kind", ""), "verdict": g.get("verdict", ""), "detail": str(g.get("detail", ""))[:GATE_DETAIL_LIMIT],
                              "approved_by": g.get("approved_by", ""), "at": g.get("at", ""), "status": s.get("status", "")})
        rj = self.out / REJECTIONS_JSON
        rejections = (read_json(rj).get("rejections") or []) if rj.is_file() else []
        model = self.args.model or (os.environ.get("OPENAI_MODEL") if self.args.builder == "openai-compat" else None) or None
        host = ""
        if self.args.builder == "openai-compat":
            try:
                host = self.llm_client().host
            except StepError:
                host = ""
        return {"run_id": self.run_id, "pipeline": pipeline,
                "executor": {"repo": "giri-skills", "git_sha": executor_sha(), "script": "scripts/deliver.py", "dry": bool(self.args.dry)},
                "builder": {"builder": self.args.builder, "provider": self.args.provider, "model": model, "base_url_host": host or None},
                "skills": skills, "approvals": approvals, "rejections": rejections, "gates": gates,
                "status": self.record.get("status", ""), "generated_at": now()}

    def write_provenance(self) -> dict:
        prov = self.provenance()
        write_json(self.evidence / PROVENANCE_JSON, prov)
        return prov

    def provenance_rows(self) -> list[str]:
        """The Provenance section of EVIDENCE.md — bullets, no timestamps (a dry run stays byte-for-byte reproducible);
        the full record with timestamps is provenance.json beside it."""
        prov = self.write_provenance()
        p, b = prov["pipeline"], prov["builder"]
        lines = ["## Provenance", "",
                 f"- Executor: giri-skills `{prov['executor']['git_sha'] or 'not a git checkout'}` · `scripts/deliver.py`",
                 f"- Pipeline: `{p['name']}` v{p['version']} · sha256 `{p['sha256']}`",
                 f"- Builder: {b['builder']}" + (f" · model {b['model']}" if b.get("model") else "") + (f" @ {b['base_url_host']}" if b.get("base_url_host") else "")
                 + f" · provider {b['provider']}"]
        if prov["skills"]:
            lines.append("- Skills (step · skill · version · sha256 of the skill directory):")
            lines += [f"  - {s['stage']}/{s['step']} · `{s['skill']}` · {s['version'] or '?'} · `{s['sha256']}`" for s in prov["skills"]]
        else:
            lines.append("- Skills: none run yet")
        if prov["approvals"]:
            lines.append("- Approvals:")
            lines += [f"  - {a['stage']}/{a['step']}: {a['by']} ({a['source']})" + (f" — {a['note']}" if a.get("note") else "") for a in prov["approvals"]]
        else:
            lines.append("- Approvals: none")
        if prov["rejections"]:
            lines.append("- Rejections:")
            lines += [f"  - {r.get('step')}: {r.get('by')} ({r.get('source', 'file')})" + (f" — {r['note']}" if r.get("note") else "") for r in prov["rejections"]]
        lines += [f"- Full record with timestamps and gate verdicts: [{PROVENANCE_JSON}]({PROVENANCE_JSON})", ""]
        return lines

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
        stubs = t.get("unfilled_stubs") or []
        warn = f" UNFILLED: {len(stubs)} scaffolded test file(s) still hold only todo stubs ({', '.join(stubs[:4])})." if stubs else ""
        return f"Tests (after the change): `{t.get('cmd')}` exit {t.get('exit')} — {verdict}{link}{inst}.{warn}"

    def acceptance_row(self) -> str:
        """The Acceptance line of EVIDENCE.md: did an independent reviewer find the change meets its requirements."""
        code = next((st for s in self.record.get("stages", []) for st in s.get("steps", [])
                     if st.get("kind") == "agent" and "acceptance" in st), None)
        if not code:
            return "Acceptance review (independent reviewer vs the requirements): NOT RUN — no code step reached it."
        a = code["acceptance"]
        if a.get("verdict") == "not_run":
            return f"Acceptance review (independent reviewer vs the requirements): NOT RUN ({a.get('detail')})."
        c = a.get("counts") or {}
        sdir = self.step_dirs.get(code["id"])
        md = sdir / ACCEPT_MD if sdir else None
        link = f" — [{ACCEPT_MD}]({md.relative_to(self.evidence)})" if md and md.is_file() else ""
        return (f"Acceptance review (independent reviewer vs the requirements, round {a.get('rounds')}): {str(a.get('verdict')).upper()} — "
                f"MET {c.get('MET', 0)}, PARTLY {c.get('PARTLY', 0)}, NOT MET {c.get('NOT_MET', 0)}, UNVERIFIED {c.get('UNVERIFIED', 0)}; "
                f"defects {a.get('defects', 0)} ({a.get('severe', 0)} critical/high){link}.")

    def bench_row(self) -> str:
        """The Benchmark line of EVIDENCE.md: whether the pipeline ran `npm run bench`, and its result."""
        code = next((st for s in self.record.get("stages", []) for st in s.get("steps", [])
                     if st.get("kind") == "agent" and "bench" in st), None)
        if not code:
            return "Benchmark (run by the pipeline): NOT RUN — no code step reached it."
        b = code["bench"]
        if b.get("skipped"):
            return f"Benchmark (run by the pipeline): NOT RUN ({b['skipped']})."
        sdir = self.step_dirs.get(code["id"])
        log = sdir / str(b.get("log") or "") if sdir else None
        link = f" — [{log.name}]({log.relative_to(self.evidence)})" if log and log.is_file() else ""
        return f"Benchmark (run by the pipeline): `{b.get('cmd')}` exit {b.get('exit')} in {b.get('duration_s')} s{link}."

    def visual_row(self) -> str:
        """The Visual line of EVIDENCE.md: what a browser saw when it opened the built app (scripts/visual_check.py)."""
        code = next((st for s in self.record.get("stages", []) for st in s.get("steps", [])
                     if st.get("kind") == "agent" and "visual" in st), None)
        if not code:
            return "Visual check (the running app): NOT RUN — no code step reached it."
        v = code["visual"]
        label = {"pass": "PASS", "fail": "FAIL", "error": "FAIL (could not run)", "not_applicable": "NOT APPLICABLE (no web UI)",
                 "off": "NOT RUN (switched off)",
                 "not_run": f"NOT RUN ({v.get('reason') or 'see visual.json'})"}.get(v.get("verdict"), str(v.get("verdict")).upper())
        sdir = self.step_dirs.get(code["id"])
        shots = [f"[{Path(x).name}]({(sdir / x).relative_to(self.evidence)})" for x in v.get("screenshots") or []
                 if sdir and (sdir / x).is_file()]
        routes = ", ".join(v.get("routes") or [])
        fails = ("; failures: " + "; ".join(v["failures"][:4])) if v.get("failures") else ""
        return (f"Visual check (the running app, desktop 1440 px and phone 390 px): {label}" + (f" — pages {routes}" if routes else "")
                + fails + (f"; screenshots: {', '.join(shots)}" if shots else "") + ".")

    def hash_files(self) -> dict:
        files = {}
        for base in (self.evidence, self.out / "build"):
            if base.is_dir():
                for p in sorted(base.rglob("*")):
                    if p.is_file():
                        files[str(p.relative_to(self.out))] = sha256(p)
        return files

    def current_stage(self) -> str:
        """The stage the run is at: the first recorded stage that has not passed, else the last one recorded."""
        stages = self.record.get("stages") or []
        return next((s["id"] for s in stages if s.get("status") != "passed"), stages[-1]["id"] if stages else "")

    def save(self, status: str, exit_code: int) -> None:
        self.record.update(status=status, exit_code=exit_code, finished_at=now())
        if self.evidence.is_dir():
            self.tracer.write(self.evidence / "trace.json")
        self.write_evidence_md()
        self.record["files"] = self.hash_files()
        write_json(self.out / "run.json", self.record)
        registry_append({"run_id": self.run_id, "pipeline": self.spec["name"], "repo": str(self.record.get("repo_input") or self.inputs.get("repo", "")),
                         "status": status, "stage": self.current_stage(), "at": self.record["finished_at"], "out": str(self.out)})

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
        self._stage_span = self.tracer.start(f"stage {stage['id']}", **{"stage.id": stage["id"], "stage.role": stage.get("role") or ""})
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
            self._close_step_span(srec["steps"][-1] if srec["steps"] else None)
            self._step_span = self.tracer.start(f"step {sid}", parent=self._stage_span, **{"step.id": sid, "step.kind": step.get("kind") or "",
                                                                                            "step.skill": step.get("skill") or ""})
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
        srec["status"] = "passed" if verdict in ("pass", "recorded", "not_run") else "failed"
        srec["duration_s"] = round(time.time() - t_stage, 3)
        self._finish_stage(srec, stage)
        return srec["status"], (EXIT_OK if srec["status"] == "passed" else EXIT_FAIL)

    def _finish_stage(self, srec: dict, stage: dict) -> None:
        self._close_step_span(srec["steps"][-1] if srec.get("steps") else None)
        if self._stage_span is not None:
            g = srec.get("gate") or {}
            self.tracer.end(self._stage_span, **{"stage.status": srec.get("status"), "gate.verdict": g.get("verdict"),
                                                  "gate.kind": g.get("kind"), "gate.detail": str(g.get("detail") or "")[:300]})
            self._stage_span = None
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


MANIFESTS = ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "requirements.txt",
             "pyproject.toml", "poetry.lock", "uv.lock")


def manifest_sha(repo: Path) -> str:
    """Hash of the dependency manifests present in the checkout (what an install depends on)."""
    h = hashlib.sha256()
    for name in MANIFESTS:
        f = repo / name
        if f.is_file():
            h.update(name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


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


def commit_preexisting_work(repo: Path) -> None:
    """A FRESH dry copy only (never on --resume, when the copy may already carry the builder's change): commit the
    person's own uncommitted work, so the code step's diff holds only the builder's change. Found on a real repo whose
    untracked docs/ from an earlier session were charged to the builder as out-of-plan files."""
    if not shutil.which("git") or not is_git_root(repo):
        return
    code, _ = git(repo, "rev-parse", "--verify", "-q", "HEAD", ok=(0, 1))
    if code != 0:
        return                                   # commit-less copy: baseline_commit takes all of it
    _, dirty = git(repo, "status", "--porcelain")
    if dirty.strip():
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "--no-verify", "-m", "baseline: uncommitted work already in the checkout before the run")


def prepare_repo(run: Run) -> None:
    src = Path(run.inputs["repo"]).expanduser()
    if run.args.dry:
        work = run.out / "repo"
        if not work.exists():
            if src.is_dir():
                shutil.copytree(src, work, ignore=COPY_IGNORE, symlinks=True)
                commit_preexisting_work(work)
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
        # owner/name = the last two path segments of any origin (https, ssh, or a local path in tests)
        m = re.search(r"[:/]([^/\s:]+/[^/\s:]+?)(?:\.git)?/?$", url.strip()) if code == 0 else None
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
    ap.add_argument("--sandbox", choices=["none", "docker"], default="none",
                    help="where project code (install, tests, benchmark, the app) runs: docker = isolated box; none = the host, recorded as NOT SANDBOXED")
    ap.add_argument("--sandbox-image", default="hostroot", help="docker image (default hostroot: the host toolchain mounted read-only)")
    ap.add_argument("--sandbox-cpus", default="2")
    ap.add_argument("--sandbox-memory", default="4g")
    ap.add_argument("--waivers", default=None, help="gate waivers file (default: <repo>/.factory/waivers.json); rule, file, reason, by[, line, expires]")
    ap.add_argument("--acceptance", choices=["auto", "on", "off"], default="auto",
                    help="independent requirements review after tests/visual pass (auto: for model builders)")
    ap.add_argument("--review-model", default=None, help="model for the acceptance reviewer (default: --model)")
    ap.add_argument("--goal", default=None, help="goal document the acceptance reviewer judges against (default: docs/*GOAL*.md in the repo)")
    ap.add_argument("--budget-usd", type=float, default=None, metavar="USD",
                    help="circuit breaker: stop the run when its model calls have cost this much (each call gets --max-budget-usd = what is left)")
    ap.add_argument("--visual", choices=["auto", "off"], default="auto",
                    help="after the tests pass, open the built web app in a browser and fail an empty or unstyled page (default auto)")
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


# ------------------------------------------------------------------ local mode: the run registry without a portal
# docs/DELIVERY-PIPELINES.md → Local mode (no portal). `deliver.py list | status | approve | reject | audit` read and
# write the run directories and <runs dir>/registry.jsonl only; nothing here touches the network.

def resume_command(base_argv: list[str]) -> str:
    """This run's command line with --resume added once — what `status` prints and the role packet ends with."""
    return shlex.join([sys.executable or "python3", str((HERE / "deliver.py").resolve())] + list(base_argv) + ["--resume"])


def load_rejections(out: Path) -> list[dict]:
    p = out / REJECTIONS_JSON
    if not p.is_file():
        return []
    data = read_json(p)
    items = data.get("rejections") if isinstance(data, dict) else None
    return [r for r in (items or []) if isinstance(r, dict) and r.get("step")]


def active_rejection(out: Path, approvals: dict, approve_all: bool) -> dict | None:
    """The latest rejection of a step that no later approval of the same step answers. `--approve-all` answers every
    rejection; an approval entry without a timestamp (a hand-written --approvals file) counts as new."""
    if approve_all:
        return None
    latest: dict[str, dict] = {}
    for r in load_rejections(out):
        if r["step"] not in latest or str(r.get("at", "")) >= str(latest[r["step"]].get("at", "")):
            latest[r["step"]] = r
    for step, r in latest.items():
        a = approvals.get(step)
        if a is None or (a.get("at") and str(a["at"]) < str(r.get("at", ""))):
            return r
    return None


def find_run(arg: str) -> Path:
    """An out directory, or a run id looked up in the runs dir (registry.jsonl first, then every <dir>/run.json)."""
    p = Path(arg).expanduser()
    if (p / "run.json").is_file():
        return p.resolve()
    d = runs_dir()
    if (d / arg / "run.json").is_file():
        return (d / arg).resolve()
    reg = d / REGISTRY_JSONL
    if reg.is_file():
        for line in reversed(reg.read_text(encoding="utf-8").splitlines()):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("run_id") == arg and e.get("out") and Path(e["out"], "run.json").is_file():
                return Path(e["out"]).resolve()
    for rj in sorted(d.glob("*/run.json")) if d.is_dir() else []:
        try:
            if read_json(rj).get("run_id") == arg:
                return rj.parent.resolve()
        except (OSError, ValueError):
            continue
    sys.exit(f"error: no run found for {arg!r} (an out directory holding run.json, or a run id under {d})")


def list_runs(d: Path) -> list[dict]:
    """Every delivery run directly under the runs dir — a <dir>/run.json with run_id, pipeline and stages (run_skill.py
    run directories live there too and are skipped)."""
    candidates = list(sorted(d.glob("*/run.json"))) if d.is_dir() else []
    reg = d / REGISTRY_JSONL   # runs started with --out elsewhere are known through the registry
    if reg.is_file():
        for line in reg.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("out") and Path(e["out"], "run.json").is_file() and Path(e["out"], "run.json") not in candidates:
                candidates.append(Path(e["out"], "run.json"))
    rows, seen = [], set()
    for rj in candidates:
        if rj.resolve() in seen:
            continue
        seen.add(rj.resolve())
        try:
            rec = read_json(rj)
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or not rec.get("run_id") or not rec.get("pipeline") or "stages" not in rec:
            continue
        stages = rec.get("stages") or []
        rows.append({"run_id": rec["run_id"], "pipeline": rec["pipeline"], "repo": str(rec.get("repo_input") or (rec.get("inputs") or {}).get("repo", "")),
                     "status": rec.get("status", ""), "stage": next((s["id"] for s in stages if s.get("status") != "passed"), stages[-1]["id"] if stages else ""),
                     "started": rec.get("started_at", ""), "finished": rec.get("finished_at", ""), "out": str(rj.parent.resolve()),
                     "dry": bool(rec.get("dry")), "builder": rec.get("builder", "")})
    rows.sort(key=lambda r: (r["started"], r["run_id"]))
    return rows


def table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(headers)]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    return "\n".join([fmt.format(*headers), fmt.format(*["-" * w for w in widths])] + [fmt.format(*[str(c) for c in r]) for r in rows])


def run_status(out: Path) -> dict:
    """The run as `status` reports it: stages with gate verdicts, the current stop (needs_approval / needs_builder /
    needs_input / wiring_error / rejected, with that file's contents) and the resume command."""
    rec = read_json(out / "run.json")
    stages = []
    for s in rec.get("stages") or []:
        g = s.get("gate") or {}
        stages.append({"id": s["id"], "role": s.get("role", ""), "status": s.get("status", ""), "gate": {"kind": g.get("kind", ""), "verdict": g.get("verdict", ""), "detail": str(g.get("detail", ""))},
                       "steps": [{"id": st["id"], "kind": st.get("kind", ""), "status": st.get("status", ""), "approved_by": st.get("approved_by", "")} for st in s.get("steps") or []],
                       "approved_by": g.get("approved_by", ""), "evidence_files": s.get("evidence_files") or []})
    stop: dict = {"kind": "none"}
    for name in ("needs_approval.json", "needs_builder.json", "needs_input.json", "wiring_error.json"):
        if (out / name).is_file():
            stop = {"kind": name[:-5], "file": str(out / name), **read_json(out / name)}
            break
    if rec.get("status") == "rejected":   # a rejection stands whatever else waits: the next resume stops on it
        stop = {**stop, "kind": "rejected", "rejection": rec.get("rejection") or {}, **({"also": stop["kind"]} if stop["kind"] != "none" else {})}
    approvals = load_approvals(str(out / APPROVALS_JSON)) if (out / APPROVALS_JSON).is_file() else {}
    cmd = rec.get("resume_command") or resume_command(rec.get("argv") or [])
    return {"run_id": rec.get("run_id", ""), "pipeline": rec.get("pipeline", ""), "version": rec.get("version", ""), "repo": str(rec.get("repo_input") or ""),
            "out": str(out), "status": rec.get("status", ""), "exit_code": rec.get("exit_code"), "dry": bool(rec.get("dry")),
            "builder": rec.get("builder", ""), "provider": rec.get("provider", ""),
            "stage": next((s["id"] for s in stages if s["status"] != "passed"), stages[-1]["id"] if stages else ""),
            "started_at": rec.get("started_at", ""), "finished_at": rec.get("finished_at", ""), "stages": stages, "stop": stop,
            "approvals": list(approvals.values()), "rejections": load_rejections(out), "resume_command": cmd, "cwd": rec.get("cwd", ""),
            "argv": rec.get("argv") or [],
            "evidence": str(out / "evidence" / "EVIDENCE.md"), "provenance": str(out / "evidence" / PROVENANCE_JSON)}


def render_status(d: dict) -> str:
    lines = [f"Run {d['run_id']} — pipeline {d['pipeline']} v{d.get('version', '')} · repo {d['repo']} · {d['status']}"
             + (f" · at {d['stage']}" if d.get("stage") else "") + (" · DRY" if d.get("dry") else "") + f" · builder {d.get('builder', '')}",
             f"Out: {d['out']}", ""]
    rows = [[s["id"], s["role"], s["status"], f"{s['gate']['kind']} {s['gate']['verdict']}".strip(), s["gate"]["detail"][:100]] for s in d["stages"]]
    lines.append(table(["Stage", "Role", "Status", "Gate", "Detail"], rows) if rows else "(no stage has run)")
    stop = d["stop"]
    lines.append("")
    if stop["kind"] == "none":
        lines.append("Stop: none" + (" — every stage passed" if d["status"] == "passed" else ""))
    elif stop["kind"] == "rejected":
        r = stop.get("rejection") or {}
        lines.append(f"Stop: rejected — step '{r.get('step', '')}' by {r.get('by', '')}: {r.get('note', '')}")
        lines.append(f"  approve it again: python3 scripts/deliver.py approve {d['out']} --step {r.get('step', '')} --by <name> [--note …]")
    elif stop["kind"] == "needs_approval":
        lines.append(f"Stop: needs approval — step '{stop.get('step', '')}' (role {stop.get('role', '')}): {stop.get('note', '')}")
        for p in stop.get("review") or []:
            lines.append(f"  review: {p}")
        lines.append(f"  approve: python3 scripts/deliver.py approve {d['out']} --step {stop.get('step', '')} --by <name> [--note …]")
    elif stop["kind"] == "needs_builder":
        lines.append(f"Stop: needs the {stop.get('role') or 'builder'} — step '{stop.get('step', '')}': {stop.get('why', '')}")
        exp = stop.get("expected")
        for name, path in (exp.items() if isinstance(exp, dict) else [(stop.get("produce", ""), exp)]):
            lines.append(f"  write {name} at {path}")
        if stop.get("prompt"):
            lines.append(f"  role packet: {stop['prompt']}")
    elif stop["kind"] == "needs_input":
        lines.append("Stop: needs input — " + ", ".join(f"{m.get('name')} ({m.get('from', '')})" for m in stop.get("missing") or []))
    elif stop["kind"] == "wiring_error":
        lines.append(f"Stop: pipeline wiring error — {stop.get('message', '')}")
    lines += ["", "Resume" + (f" (from {d['cwd']})" if d.get("cwd") else "") + ":", f"  {d['resume_command']}"]
    return "\n".join(lines)


def cmd_list(args) -> int:
    d = Path(args.runs).expanduser() if args.runs else runs_dir()
    rows = list_runs(d)
    if args.json:
        print(json.dumps({"runs_dir": str(d), "runs": rows}, indent=2))
        return 0
    if not rows:
        print(f"no delivery runs under {d}")
        return 0
    print(table(["Run", "Pipeline", "Repo", "Status", "Stage", "Started", "Out"],
                [[r["run_id"], r["pipeline"], r["repo"], r["status"], r["stage"], r["started"], r["out"]] for r in rows]))
    return 0


def cmd_status(args) -> int:
    out = find_run(args.run)
    d = run_status(out)
    print(json.dumps(d, indent=2) if args.json else render_status(d))
    return 0


def _write_decision(out: Path, name: str, key: str, entry: dict) -> list[dict]:
    """Merge one approval / rejection into <out>/<name> ({key: [ … ]}); the latest entry per step wins on read."""
    p = out / name
    data = read_json(p) if p.is_file() else {}
    items = [x for x in (data.get(key) if isinstance(data, dict) else None) or [] if isinstance(x, dict)]
    if name == APPROVALS_JSON:
        items = [x for x in items if x.get("step") != entry["step"]]   # one approval per step: the newest replaces it
    items.append(entry)
    write_json(p, {key: items})
    return items


def cmd_approve(args) -> int:
    out = find_run(args.run)
    rec = read_json(out / "run.json")
    entry = {"step": args.step, "by": args.by, "note": args.note or "", "at": now_precise(), "source": args.source}
    _write_decision(out, APPROVALS_JSON, "approvals", entry)
    registry_append({"run_id": rec.get("run_id", ""), "pipeline": rec.get("pipeline", ""), "repo": str(rec.get("repo_input") or ""),
                     "status": "approved", "stage": next((s["id"] for s in rec.get("stages") or [] if any(st.get("id") == args.step for st in s.get("steps") or [])), ""),
                     "step": args.step, "by": args.by, "at": entry["at"], "out": str(out)})
    cmd = rec.get("resume_command") or resume_command(rec.get("argv") or [])
    if args.json:
        print(json.dumps({"run_id": rec.get("run_id", ""), "out": str(out), "approval": entry, "file": str(out / APPROVALS_JSON), "resume_command": cmd}, indent=2))
    else:
        print(f"approved step '{args.step}' by {args.by} — recorded in {out / APPROVALS_JSON}", "", "Resume:", f"  {cmd}", sep="\n")
    return 0


def cmd_reject(args) -> int:
    out = find_run(args.run)
    rec = read_json(out / "run.json")
    stage = next((s["id"] for s in rec.get("stages") or [] if any(st.get("id") == args.step for st in s.get("steps") or [])), "")
    entry = {"step": args.step, "stage": stage, "by": args.by, "note": args.note, "at": now_precise(), "source": args.source}
    _write_decision(out, REJECTIONS_JSON, "rejections", entry)
    rec.update(status="rejected", exit_code=EXIT_APPROVAL, rejection=entry, finished_at=entry["at"])
    write_json(out / "run.json", rec)
    registry_append({"run_id": rec.get("run_id", ""), "pipeline": rec.get("pipeline", ""), "repo": str(rec.get("repo_input") or ""),
                     "status": "rejected", "stage": stage, "step": args.step, "by": args.by, "at": entry["at"], "out": str(out)})
    cmd = rec.get("resume_command") or resume_command(rec.get("argv") or [])
    if args.json:
        print(json.dumps({"run_id": rec.get("run_id", ""), "out": str(out), "rejection": entry, "file": str(out / REJECTIONS_JSON), "resume_command": cmd}, indent=2))
    else:
        print(f"rejected step '{args.step}' by {args.by}: {args.note} — recorded in {out / REJECTIONS_JSON}; the run is marked rejected "
              f"(a resume stops with exit 3 until the step is approved again: deliver.py approve {out} --step {args.step} --by <name>)")
    return 0


def render_audit_md(prov: dict) -> str:
    """provenance.json as an auditor reads it: what ran, at which version and hash, who approved what and when."""
    p, b, e = prov.get("pipeline") or {}, prov.get("builder") or {}, prov.get("executor") or {}
    lines = [f"# Audit — run {prov.get('run_id', '')}", "",
             f"Pipeline `{p.get('name', '')}` v{p.get('version', '')} (sha256 `{p.get('sha256', '')}`) · status {prov.get('status', '')}"
             + (" · DRY RUN" if e.get("dry") else ""), "",
             f"Executor: giri-skills `{e.get('git_sha') or 'not a git checkout'}` · `{e.get('script', '')}` · builder {b.get('builder', '')}"
             + (f" · model {b['model']}" if b.get("model") else "") + (f" @ {b['base_url_host']}" if b.get("base_url_host") else "")
             + f" · provider {b.get('provider', '')} · generated {prov.get('generated_at', '')}", "",
             "## Skills", "", "| Stage | Step | Skill | Version | sha256 (skill directory) |", "|---|---|---|---|---|"]
    lines += [f"| {s.get('stage', '')} | {s.get('step', '')} | `{s.get('skill', '')}` | {s.get('version') or '?'} | `{s.get('sha256', '')}` |" for s in prov.get("skills") or []] or ["| — | — | none run | | |"]
    lines += ["", "## Approvals", "", "| Stage | Step | By | Note | At | Source |", "|---|---|---|---|---|---|"]
    lines += [f"| {a.get('stage', '')} | {a.get('step', '')} | {a.get('by', '')} | {a.get('note', '')} | {a.get('at', '')} | {a.get('source', '')} |" for a in prov.get("approvals") or []] or ["| — | — | none | | | |"]
    lines += ["", "## Rejections", "", "| Stage | Step | By | Note | At | Source |", "|---|---|---|---|---|---|"]
    lines += [f"| {r.get('stage', '')} | {r.get('step', '')} | {r.get('by', '')} | {r.get('note', '')} | {r.get('at', '')} | {r.get('source', '')} |" for r in prov.get("rejections") or []] or ["| — | — | none | | | |"]
    lines += ["", "## Gates", "", "| Stage | Kind | Verdict | Approved by | At | Detail |", "|---|---|---|---|---|---|"]
    lines += [f"| {g.get('stage', '')} | {g.get('kind', '')} | {g.get('verdict', '')} | {g.get('approved_by', '')} | {g.get('at', '')} | {str(g.get('detail', '')).replace('|', '¦')[:200]} |" for g in prov.get("gates") or []] or ["| — | — | none | | | |"]
    return "\n".join(lines) + "\n"


def cmd_audit(args) -> int:
    out = find_run(args.run)
    pj = out / "evidence" / PROVENANCE_JSON
    if not pj.is_file():
        sys.exit(f"error: {pj} not found — the run has not written its evidence yet")
    prov = read_json(pj)
    print(json.dumps(prov, indent=2) if args.json else render_audit_md(prov), end="" if not args.json else "\n")
    return 0


def local_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="deliver.py", description="Local mode — the run registry without a portal (docs/DELIVERY-PIPELINES.md → Local mode)")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list", help="table of the delivery runs under the runs dir (SF_RUNS_DIR, else runs/)")
    p.add_argument("--runs", metavar="DIR", help="runs directory (default: $SF_RUNS_DIR or runs/)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("status", help="stage table, the current stop and the resume command of one run")
    p.add_argument("run", help="the run's out directory, or its run id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("approve", help="record an approval of a step in <out>/approvals.json; prints the resume command")
    p.add_argument("run", help="the run's out directory, or its run id")
    p.add_argument("--step", required=True, help="the approval step id (needs_approval.json `step`)")
    p.add_argument("--by", required=True, help="who approves")
    p.add_argument("--note", default="", help="why")
    p.add_argument("--source", default="file", choices=["file", "mcp"], help=argparse.SUPPRESS)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("reject", help="record a rejection in <out>/rejections.json and mark the run rejected")
    p.add_argument("run", help="the run's out directory, or its run id")
    p.add_argument("--step", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--note", required=True, help="why — a resume prints it until the step is approved again")
    p.add_argument("--source", default="file", choices=["file", "mcp"], help=argparse.SUPPRESS)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_reject)
    p = sub.add_parser("audit", help="print the run's provenance (skills, versions, hashes, approvals, gates)")
    p.add_argument("run", help="the run's out directory, or its run id")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true", help="provenance.json as it is")
    g.add_argument("--md", action="store_true", help="an EVIDENCE-style Markdown record for an auditor (default)")
    p.set_defaults(fn=cmd_audit)
    args = ap.parse_args(argv)
    return args.fn(args)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in LOCAL_COMMANDS:
        return local_main(argv)
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
    # approvals: <out>/approvals.json (written by `deliver.py approve`, or by hand) first, --approvals on top
    approvals = {**load_approvals(str(out / APPROVALS_JSON) if (out / APPROVALS_JSON).is_file() else None), **load_approvals(args.approvals)}

    run.spec_path = spec_path if spec_path.is_file() else ((out / "pipeline.json") if (out / "pipeline.json").is_file() else None)
    base_argv = [a for a in argv if a != "--resume"]
    run.record = {"run_id": run.run_id, "pipeline": spec["name"], "version": spec.get("version", ""), "mode": spec.get("mode", ""),
                  "dry": bool(args.dry), "builder": args.builder, "provider": args.provider, "inputs": given,
                  "repo_input": repo_key, "out": str(out), "started_at": (prev_record or {}).get("started_at") or now(),
                  "resumed": bool(prev_record), "stages": list((prev_record or {}).get("stages") or []),
                  "argv": base_argv, "cwd": os.getcwd(), "resume_command": resume_command(base_argv)}
    rejection = active_rejection(out, approvals, bool(args.approve_all))
    if rejection:
        # `deliver.py reject` stands until the same step is approved again (an approval recorded after it, or --approve-all)
        kept = dict(prev_record or run.record)   # the earlier record stands (base_sha, baseline, hashes); only the status changes
        kept.update(status="rejected", exit_code=EXIT_APPROVAL, rejection=rejection, finished_at=now())
        write_json(out / "run.json", kept)
        write_json(out / "needs_approval.json", {
            "run_id": run.run_id, "pipeline": spec["name"], "stage": rejection.get("stage", ""), "step": rejection["step"],
            "rejected": rejection, "note": rejection.get("note", ""),
            "how": f"rejected by {rejection.get('by', '')}: {rejection.get('note', '')} — record a new approval of step "
                   f"'{rejection['step']}' (deliver.py approve {out} --step {rejection['step']} --by <name>), then re-run with --resume"})
        registry_append({"run_id": run.run_id, "pipeline": spec["name"], "repo": repo_key, "status": "rejected",
                         "stage": rejection.get("stage", ""), "at": now(), "out": str(out)})
        print(f"{spec['name']} run {run.run_id}: rejected at step '{rejection['step']}' by {rejection.get('by', '')}: "
              f"{rejection.get('note', '')} — approve the step again, then --resume", file=sys.stderr)
        return EXIT_APPROVAL
    registry_append({"run_id": run.run_id, "pipeline": spec["name"], "repo": repo_key, "status": "running",
                     "stage": run.current_stage(), "at": now(), "out": str(out)})
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
    try:
        run.sandbox.prepare()            # --sandbox docker without a reachable daemon stops here, never falls back silently
    except sbx.SandboxError as e:
        print(f"error: {e}", file=sys.stderr)
        run.save("failed", EXIT_FAIL)
        return EXIT_FAIL

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
        if code != EXIT_OK:
            run.export_telemetry()          # the run stops here: export once, before the final save writes trace.json
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
    run.export_telemetry()
    run.save("passed", EXIT_OK)
    verdicts = [(st.get("gate") or {}).get("verdict") for st in run.record.get("stages", [])]
    passed, not_run = sum(v == "pass" for v in verdicts), sum(v == "not_run" for v in verdicts)
    auto = sum(1 for st in run.record.get("stages", []) for x in st.get("steps", []) if x.get("approved_by") == "--approve-all")
    extra = (f", {not_run} not run (dry)" if not_run else "") + (f", {auto} approval(s) auto-approved" if auto else "")
    print(f"{spec['name']} run {run.run_id}: {passed} of {len(spec['stages'])} stages passed{extra} — evidence in {run.evidence / 'EVIDENCE.md'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
