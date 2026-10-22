# Delivery pipelines — how a request becomes shipped software

A **pipeline** is the factory's unit of work. Every request — a new app, a feature on an existing one, a migration,
a fix — enters a pipeline and leaves it with real artifacts and gate evidence. Pipelines are templates kept in
`pipelines/*.json`; roles own stages; stages run the library's published skills; the executor
(`scripts/deliver.py`, dispatched by the portal or an IDE) runs them against a real repository and opens a pull
request that carries the evidence. The portal is the control plane (submit, authorise, watch, audit); the executor is
where code can run (GitHub Actions, a developer's machine, Claude Code).

This is the Port.io model with AI roles doing the work: the catalog knows the repos and their stack, the pipeline is a
self-service action, the scorecard is the evidence, and a person approves the plan and merges the PR.

## The model

```
request ─► pipeline (template) ─► stages ─► role ─► skills ─► gate ─► evidence
            │                        │
            │  stack profile ────────┘  (read from the repo once, passed to every stage)
            └─ inputs: repo + ref (brownfield) or brief (greenfield), request text, extras
```

| Term | Meaning |
|---|---|
| **Pipeline** | A template: ordered stages, the ADLC stages it covers, the kinds of request it fits (`fits`), its inputs |
| **Stage** | One ADLC stage (`shared/adlc-stages.json`), owned by one **role** (`roles/*.json`), running one or more **steps** |
| **Step** | A published skill run (`skill`), an agent step that writes code (`agent`), or a human approval (`approval`) |
| **Gate** | A rule the stage must satisfy before the next stage runs: a check on an output, a skill exit code, or a human approval |
| **Evidence** | What the run records per stage: the skill's own report, the gate verdict, who approved, hashes of every file |
| **Stack profile** | Facts read from the repo before stage 1: language flavour, framework, package manager, test runner, deploy target, migrations dir. Every stage receives it; skills that write files honour it ("read before write") |

## Pipeline file (`pipelines/<name>.json`)

`pipelines/feature-delivery.json` as shipped (validated by `scripts/validate_pipelines.py`; `pipelines/greenfield-app.json`
is the same with a `bootstrap` stage in front):

```json
{
  "name": "feature-delivery",
  "version": "0.1.0",
  "title": "Feature delivery on an existing application",
  "description": "Brownfield: a feature request on a repository the catalog knows, through requirements, architecture, build, evaluate, deploy and operate. Every step runs a published skill with its real input and output names; compose steps derive the files a later skill needs from what earlier steps wrote, deterministically.",
  "mode": "brownfield",
  "fits": { "stacks": ["nextjs"], "request_kinds": ["feature", "fix", "hardening"] },
  "inputs": [
    { "name": "repo",    "type": "repo",   "required": true,  "from": "catalog repository (owner/name) or a local checkout" },
    { "name": "ref",     "type": "string", "required": false, "from": "branch or commit to start from (default: the checkout as it is)" },
    { "name": "request", "type": "text",   "required": true,  "from": "the feature request in the requester's words" },
    { "name": "brief",   "type": "json",   "required": false, "from": "product brief for product-spec-prd (layout: skills/build/product-spec-prd/assets/brief-template.json); may carry `files` (repo-relative source files the feature touches) or `tasks` [{task, accept, test, files}]" }
  ],
  "stack_profile": { "from": "repo", "detect": "scripts/stack_profile.py" },
  "stages": [
    {
      "id": "requirements", "adlc_stage": "requirements", "role": "ai-product-manager",
      "steps": [
        { "id": "brief", "kind": "compose", "derive": "brief-from-request",
          "inputs": { "request": "$in.request", "brief": "$in.brief" }, "outputs": ["brief.json"] },
        { "id": "prd", "kind": "skill", "skill": "build/product-spec-prd",
          "inputs": { "brief": "$steps.brief:brief.json", "draft_only": "$run.draft_only" } }
      ],
      "gate": { "kind": "output", "step": "prd", "file": "prd-final.md", "check": "sections:[\"Acceptance criteria\"]" },
      "evidence": ["$steps.brief:brief.json", "$steps.prd:prd-final.md"]
    },
    {
      "id": "architecture", "adlc_stage": "architecture", "role": "ai-solution-architect",
      "steps": [
        { "id": "spec", "kind": "compose", "derive": "spec-from-prd",
          "inputs": { "brief": "$steps.brief:brief.json", "prd": "$steps.prd:prd-final.md", "request": "$in.request" },
          "outputs": ["spec.md", "spec.json"] },
        { "id": "plan", "kind": "skill", "skill": "build/spec-to-plan",
          "inputs": { "spec": "$steps.spec:spec.md", "section": "$steps.spec:spec.json#section", "repo": "$repo" } },
        { "id": "plan-approval", "kind": "approval", "role": "ai-solution-architect", "note": "Approve the plan before any code is written; edit plan.md / tasks.csv in the step folder first if files or tests are missing" }
      ],
      "gate": { "kind": "approval", "step": "plan-approval" },
      "evidence": ["$steps.plan:plan.md", "$steps.plan:tasks.csv"]
    },
    {
      "id": "build", "adlc_stage": "build", "role": "full-stack-engineer",
      "steps": [
        { "id": "feature", "kind": "compose", "derive": "feature-from-plan",
          "inputs": { "plan": "$steps.plan:plan.md", "tasks": "$steps.plan:tasks.csv", "brief": "$steps.brief:brief.json" },
          "outputs": ["feature.md", "feature.json"] },
        { "id": "tests", "kind": "skill", "skill": "build/test-strategy-tdd",
          "inputs": { "feature": "$steps.feature:feature.md", "files": "$steps.feature:feature.json#files", "target": "$repo" } },
        { "id": "code", "kind": "agent", "agent": "claude-code",
          "inputs": { "plan": "$steps.plan:plan.md", "tests": "$steps.tests:test-plan.md", "target": "$repo" },
          "constraints": ["skills/build/nextjs-enterprise-conventions/SKILL.md", "shared/stack-conventions.md"] },
        { "id": "conventions", "kind": "skill", "skill": "build/nextjs-enterprise-conventions",
          "inputs": { "target": "$repo", "baseline": "$profile.baselines.nextjs" }, "gate": true }
      ],
      "gate": { "kind": "exit", "step": "conventions" },
      "evidence": ["$steps.tests:test-plan.md", "$steps.tests:scaffold-report.json", "$steps.code:diff.patch", "$steps.code:agent-summary.md", "$steps.conventions:report.md"]
    },
    {
      "id": "evaluate", "adlc_stage": "evaluate", "role": "ai-quality-red-team",
      "steps": [
        { "id": "review",   "kind": "skill", "skill": "build/code-review-runner",  "inputs": { "diff": "$steps.code:diff.patch", "spec": "$steps.prd:prd-final.md" } },
        { "id": "security", "kind": "skill", "skill": "build/security-review",     "inputs": { "diff": "$steps.code:diff.patch", "target": "$repo", "draft_only": "$run.draft_only" } },
        { "id": "perf",     "kind": "skill", "skill": "build/perf-review-runner",  "inputs": { "target": "$repo", "baseline": "$profile.baselines.perf" } },
        { "id": "ui",       "kind": "skill", "skill": "build/ui-component-quality", "inputs": { "target": "$repo", "baseline": "$profile.baselines.ui" } }
      ],
      "gate": { "kind": "all", "of": [
        { "kind": "output", "step": "review", "file": "review.md", "check": "contains:\"Verdict: **PASS**\"" },
        { "kind": "exit", "step": "security" },
        { "kind": "exit", "step": "perf" },
        { "kind": "exit", "step": "ui" }
      ] },
      "evidence": ["$steps.review:review.md", "$steps.security:security-review.md", "$steps.perf:report.md", "$steps.ui:report.md"]
    },
    {
      "id": "deploy", "adlc_stage": "deploy", "role": "mlops-platform-engineer",
      "steps": [
        { "id": "ci", "kind": "skill", "skill": "build/ci-cd-vercel-github", "inputs": { "target": "$repo" } },
        { "id": "pr", "kind": "pr", "title": "$in.request", "branch": "deliver/$run.id", "body": "$evidence" }
      ],
      "gate": { "kind": "external", "what": "CI green on the pull request" },
      "evidence": ["$steps.ci:ci-report.md", "$steps.pr:pr.json"]
    },
    {
      "id": "operate", "adlc_stage": "operate", "role": "ai-ops-sre",
      "steps": [
        { "id": "handoff", "kind": "skill", "skill": "build/handoff-and-thread-close", "inputs": { "target": "$repo", "state": "$run.state" } }
      ],
      "gate": { "kind": "output", "step": "handoff", "file": "HANDOFF.md", "check": "exists" },
      "evidence": ["$steps.handoff:HANDOFF.md"]
    }
  ],
  "outputs": ["$steps.pr:pr.json", "$evidence"]
}
```

Where the shipped file differs from the first sketch, and why (every name is the skill's real contract — check with
`python3 scripts/run_skill.py --explain build/<skill>`):

| Sketch | Shipped | Why |
|---|---|---|
| `product-spec-prd` took `request` and wrote `prd.md` | a `brief-from-request` **compose** step writes `brief.json` (the brief given, else `{feature, problem}` from the request); the skill takes `brief` and writes `prd-final.md` | the skill's only required input is `brief`; `request` is not an input it declares |
| `spec-to-plan` took `spec: prd.md, section: $in.request` | a `spec-from-prd` compose step writes `spec.md` (one bullet per v1 scope item / brief task, `files:` when the brief names them) and `spec.json#section` | `spec-to-plan` plans the first heading containing `section` and needs bullets under it; a PRD has neither |
| `test-strategy-tdd` read `feature.md` and `plan.json#files` from the plan step | a `feature-from-plan` compose step derives `feature.md` (one criterion per task) and `feature.json#files` from `tasks.csv`; output is `test-plan.md`, not `tests-report.md` | `spec-to-plan` writes `plan.md` + `tasks.csv` only |
| evaluate gate: review PASS + security exit | plus `perf` and `ui` exit gates | each of those skills exits 1 on new high findings — a verdict the stage must honour |
| handoff gate on `docs/HANDOFF.md` | `HANDOFF.md` in the step folder | the skill writes `{out}/HANDOFF.md`; `--write-to-repo` is not used by the pipeline |
| `$run.draft_only` did not exist | `product-spec-prd` and `security-review` get `draft_only=true` when the provider is `dry` or `none` | their model step cannot run without a provider; the script draft is then the final, labelled as such |

### References
| Reference | Resolves to |
|---|---|
| `$in.<name>` | a pipeline input |
| `$repo` | the working checkout of the target repository (a `path` input to skills) |
| `$profile.<key>` | a stack-profile fact (`flavour`, `framework`, `package_manager`, `test_runner`, `deploy_target`, `migrations_dir`, `baselines.<check>`) |
| `$steps.<id>:<file>[#json.key]` | an output file of an earlier step (same syntax as playbooks) |
| `$run.id`, `$run.state`, `$run.draft_only` | the run id; the run's honest state line for the handoff; `true` when the provider is `dry` or `none` (skills with a model step take their script draft as final) |
| `$evidence` | the evidence bundle so far (`evidence/EVIDENCE.md`) |

A plain string that is not a reference is a literal. Only the executor's own values exist: a template cannot name an
arbitrary `$run.*` or `$profile.*` key (the validator rejects it).

### Step kinds
| Kind | Runs | Records |
|---|---|---|
| `skill` | a published library skill via `run_skill.py`; `gate: true` means exit 1 blocks the stage; an optional input that resolves to nothing is omitted; exit 2 (missing input) fails the stage with the input named | run.json, outputs, checks |
| `compose` | a deterministic derivation of a file a later skill needs from what earlier steps wrote (`brief-from-request`, `spec-from-prd`, `feature-from-plan` — implemented in `scripts/deliver.py`, nothing invented, unknowns left to the skills' TBD markers) | the declared `outputs` |
| `agent` | a coding agent (`claude-code` first) on the checkout, constrained by the listed files and the plan; it may only touch files the plan names. `--builder none` stops the run (exit 4, `needs_builder.json`) for a person or IDE agent; `--builder manual` records a diff supplied at `<out>/build/diff.patch` | diff.patch, files-changed.json (files outside the plan are flagged), agent-summary.md |
| `approval` | waits for a person holding the stage's role (portal) or the requester (IDE); on the CLI, `--approve-all` or an `--approvals approvals.json` file (`{"approvals": [{"step", "by", "note"}]}`) satisfies it, otherwise the run stops with exit 3 and `needs_approval.json` | approval.json: who, when, note |
| `pr` | on the checkout: branch `deliver/<run-id>`, the checkout's changes committed as `skills-factory[bot]`, `gh auth setup-git` when `GH_TOKEN` is set, push to `origin`, then `gh pr create --title <title> --body-file EVIDENCE.md` with cwd = the checkout; `--dry` writes `pr.json` with `{"dry": true}` and touches nothing | pr.json (number, url, head sha, committed_as) |

### Gate kinds
`output` (a check on a step's file, check vocabulary of `scripts/check_output.py`), `exit` (step exit code 0),
`approval`, `all` / `any` (combinations), `external` (recorded, satisfied outside the run, e.g. CI on the PR).

### Stack profile (`scripts/stack_profile.py <repo>` → `stack-profile.json`)
Read once, before stage 1, never guessed: `flavour` (ts|js), `framework` (nextjs|…), `package_manager`, `test_runner`
(vitest|jest|pytest|none), `e2e` (playwright|none), `deploy_target` (vercel|aws|azure|gcp|fly|railway|unknown),
`migrations_dir` (or null), `monorepo_root`, `baselines` (paths to recorded findings.csv per check when present:
`docs/baselines/<nextjs|perf|ui>-findings.csv` in the repo, else null). Every fact carries its `evidence` (the file it
was read from); a missing or empty directory profiles as unknowns. `flavour` is `ts | js | python | unknown`.
Skills that write files must honour it; skills that lint read it for file selection.
A greenfield pipeline sets `"stack_profile": {"after": "bootstrap"}`: the profile is read after that stage, because
before it there is nothing to read.

## Roles own stages
`roles/<role>.json` gains `"stages": ["requirements", …]` — the ADLC stages the role may own. A pipeline validates
that every stage's role lists that stage and that the role's `skills` include every skill the stage runs
(`scripts/validate_pipelines.py`, called from `scripts/validate.py`). Owners today: ai-product-manager (requirements),
ai-solution-architect (architecture; gained `build/spec-to-plan`), full-stack-engineer (build), ai-quality-red-team
(evaluate; gained `build/code-review-runner`, `build/security-review`, `build/perf-review-runner`,
`build/ui-component-quality`), mlops-platform-engineer (deploy), ai-ops-sre (operate; gained
`build/handoff-and-thread-close`). At run time
the portal checks `sf_pipeline_access` (who may start the pipeline) and records the owning role per stage in the
evidence; an approval step is satisfied only by a member assigned to the stage's role.

## Where it runs
| Entry | Executor | Human gates |
|---|---|---|
| Portal → Deliver | GitHub Actions `.github/workflows/delivery.yml` in giri-skills, dispatched (`workflow_dispatch`) with `run_id, pipeline, mode, repo, ref, request, callback` | approval in the portal (the executor polls for it); merge on the PR |
| IDE (Claude Code, Cursor) → MCP `deliver` | the same `scripts/deliver.py` on the developer's machine with `--run <id> --portal <url>` (the portal prints the command); evidence posted to the portal | approval in the portal or the terminal; merge on the PR |
| CI (`deliver.py --dry`) | `validate.yml` step "Delivery pipelines (dry)" runs feature-delivery on `tests/fixtures/delivery-repo`; `tests/test_deliver.py` dry-runs both templates | none |

### The GitHub executor (`delivery.yml`)
One job per run (concurrency group `delivery-<run_id>`): checkout giri-skills; Python 3.12 + Node 22; checkout the
target `inputs.repo` at `inputs.ref` (default branch when empty) into `target/`; `npm i -g @anthropic-ai/claude-code`;
`python3 scripts/deliver.py --pipeline … --repo target --request … --run <run_id> --portal <callback> --run-id <run_id>
--builder claude-code --provider anthropic --out delivery-out`; upload `delivery-out/evidence` (plus run.json,
callback.log, needs_*.json) as the artifact `evidence-<run_id>` — always, even when a gate fails; write EVIDENCE.md
into the job summary. Workflow inputs never reach a `run:` script as expressions; they are passed through env.

Three repository secrets (giri-skills → Settings → Secrets and variables → Actions):

| Secret | Used by | Scope |
|---|---|---|
| `DELIVERY_TOKEN` | target checkout (`token:`), `GH_TOKEN` for the pr step (`gh auth setup-git`, push `deliver/<run-id>`, `gh pr create`) | fine-grained PAT or GitHub App token with **contents: write** and **pull-requests: write** on the target repositories |
| `ANTHROPIC_API_KEY` | the build step's Claude Code (`claude -p`) and every skill's model step (`--provider anthropic`) | an Anthropic API key |
| `SF_API_KEY` | `scripts/deliver.py` → `POST /api/delivery-runs/<id>/stage`, `GET /api/delivery-runs/<id>` | a portal API key (`sf_live_…`) of the workspace, created by a member who holds the pipeline's role (API-key reads and writes are scoped to that workspace) |

The portal side needs `DELIVERY_GITHUB_TOKEN` (Actions: write on giri-skills) to dispatch the workflow —
`studio/.env.example`.

### The portal callback (`--run <id> --portal <url>`, key in `SF_API_KEY`)
The executor posts one `DeliveryStageInput` (`studio/lib/validation.ts`) to `<portal>/api/delivery-runs/<id>/stage`:

| When | Stage record |
|---|---|
| after the stack profile | `{id: <first pending stage>, status: running, stack_profile: {...}}` — the profile travels only on the first post |
| after every stage | `status` succeeded (gate pass/recorded) · blocked (gate fail, or waiting for the builder with verdict `pending`) · awaiting_approval; `gate {kind, verdict, detail}`; `evidence [{path, sha256, bytes}]` for the stage's evidence files and its `gate.json` (paths relative to `evidence/`); `started_at` / `finished_at` in UTC |
| the stage with the `pr` step | plus `pr {number, url, head_sha}` (never in `--dry`) |
| the stack profile or the checkout fails | `status: failed` with `error` |
| every post | `executor_ref` when GitHub Actions sets `GITHUB_RUN_URL` (or `GITHUB_SERVER_URL` + `GITHUB_REPOSITORY` + `GITHUB_RUN_ID`) |

A post that fails is retried 3× with backoff (1 s, 2 s; `SF_CALLBACK_BACKOFF` overrides), every attempt is logged
to `<out>/callback.log`, a warning is printed and the run continues — the evidence bundle is the record, the portal
is the mirror. An **approval** step in portal mode posts `awaiting_approval`, then polls `GET /api/delivery-runs/<id>`
every `--poll-interval` (30 s) until `approvals[]` holds that stage, up to `--approval-timeout` (3600 s); the approval
is recorded in `approval.json` (by, note) and the run continues — so approving in the portal resumes the CI run.
After the timeout the run stops with exit 3 as it would without a portal. `--approve-all` and `--approvals` skip the poll.

## The executor (`scripts/deliver.py`)

```
python3 scripts/deliver.py <pipeline> | --pipeline <name> --repo <path> --request "<text>" [--brief brief.json] [--ref <ref>]
    [--input name=value …] [--out <dir>] --builder none|manual|claude-code [--provider dry|none|anthropic|openai]
    [--approve-all | --approvals approvals.json] [--patch diff.patch] [--dry] [--resume] [--run-id ID]
    [--run <portal run id> --portal <url> [--approval-timeout 3600] [--poll-interval 30]]   # SF_API_KEY in env
```

`--out` is required unless `--run` is given, when it defaults to `runs/<run id>` under giri-skills — the command the
portal prints (`deliverCommand`) therefore runs as printed.

| Exit | Meaning |
|---|---|
| 0 | every stage passed |
| 1 | a gate or step failed — the evidence so far is in `<out>/evidence/` |
| 2 | bad arguments or a missing pipeline input (`needs_input.json`) |
| 3 | waiting for an approval (`needs_approval.json`); re-run with `--resume` and `--approvals` |
| 4 | waiting for the builder (`needs_builder.json`); drop the diff at `<out>/build/diff.patch`, re-run with `--resume` |

`--dry` works on a copy of the repo under `<out>/repo` (git-initialised with a fixed identity and date so the run is
reproducible; a manual diff is applied to that copy so the lint and review stages assess the change; nothing is pushed).
Without `--dry` the checkout is used in place and the `pr` step needs `gh`. `--resume` keeps every completed step of
the first incomplete stage and re-runs the rest. The run id is derived from pipeline + request + repo (plus a time
suffix outside `--dry`), so a dry run is deterministic apart from the timestamps in `run.json` and `gate.json`.

## When no template fits
`scripts/compose_pipeline.py --stack <profile> --request-kind <kind>` assembles a pipeline from the catalog: one
stage per ADLC stage the request kind needs, the role whose `stages` lists it, the role's skills whose `fits`
matches the stack. The composed file is saved under `pipelines/composed/` and validated like any template.

## Evidence bundle
`evidence/` in the run: `stack-profile.json`, one folder per stage (`<nn>-<stage>/<step>/…` — every step's outputs
and run_skill log) with `gate.json` (`{verdict, kind, detail, role, approved_by, at}`; verdict `pass | fail |
recorded | pending`), and `EVIDENCE.md` — the table that goes into the PR body (relative links only, so the bundle
travels). `<out>/run.json` records the stages, steps, exit codes, durations and the sha256 of every evidence file:

| Stage | Role | Gate | Verdict | Evidence |
|---|---|---|---|---|

## Definition of done for the factory
1. Every request enters a pipeline (portal or IDE) and exits with artifacts and gate evidence.
2. Templates cover greenfield and brownfield; a stack profile drives every stage; composition covers the rest.
3. Roles own stages and approvals; the portal records who did what.
4. The executor opens a real PR on a real repo; CI on that PR is the deploy gate.
5. Everything above is tested: pipeline validation, a dry run of every template in CI, executor tests, portal tests.
