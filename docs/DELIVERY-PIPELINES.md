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
| **Pipeline** | A template: ordered stages, the ADLC stages it covers, the kinds of request it fits (`fits`), its inputs — or one composed from the catalog when no template fits |
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
        { "id": "plan-refine", "kind": "agent", "agent": "claude-code", "produces": ["plan.md", "tasks.csv"],
          "inputs": { "plan": "$steps.plan:plan.md", "tasks": "$steps.plan:tasks.csv", "prd": "$steps.prd:prd-final.md", "request": "$in.request", "target": "$repo" } },
        { "id": "plan-approval", "kind": "approval", "role": "ai-solution-architect", "note": "Approve the refined plan before any code is written: every task names its files, acceptance, test and rollback (the gate refuses a plan with TBD cells)" }
      ],
      "gate": { "kind": "all", "of": [
        { "kind": "output", "step": "plan-refine", "file": "tasks.csv", "check": "csv_rows:files!empty" },
        { "kind": "output", "step": "plan-refine", "file": "tasks.csv", "check": "csv_rows:acceptance!empty" },
        { "kind": "output", "step": "plan-refine", "file": "tasks.csv", "check": "csv_rows:files!tbd" },
        { "kind": "output", "step": "plan-refine", "file": "tasks.csv", "check": "csv_rows:acceptance!tbd" },
        { "kind": "output", "step": "plan-refine", "file": "tasks.csv", "check": "csv_rows:test!tbd" },
        { "kind": "approval", "step": "plan-approval" }
      ] },
      "evidence": ["$steps.plan:plan.md", "$steps.plan:tasks.csv", "$steps.plan-refine:plan.md", "$steps.plan-refine:tasks.csv"]
    },
    {
      "id": "build", "adlc_stage": "build", "role": "full-stack-engineer",
      "steps": [
        { "id": "feature", "kind": "compose", "derive": "feature-from-plan",
          "inputs": { "plan": "$steps.plan-refine:plan.md", "tasks": "$steps.plan-refine:tasks.csv", "brief": "$steps.brief:brief.json" },
          "outputs": ["feature.md", "feature.json"] },
        { "id": "files", "kind": "agent", "agent": "claude-code", "produces": ["files.txt"],
          "inputs": { "plan": "$steps.plan-refine:plan.md", "tasks": "$steps.plan-refine:tasks.csv", "target": "$repo" } },
        { "id": "tests", "kind": "skill", "skill": "build/test-strategy-tdd",
          "inputs": { "feature": "$steps.feature:feature.md", "files": "$steps.files:files.txt#csv", "target": "$repo" } },
        { "id": "code", "kind": "agent", "agent": "claude-code",
          "inputs": { "plan": "$steps.plan-refine:plan.md", "tests": "$steps.tests:test-plan.md", "files": "$steps.files:files.txt", "target": "$repo" },
          "constraints": ["skills/build/nextjs-enterprise-conventions/SKILL.md", "shared/stack-conventions.md"] },
        { "id": "conventions", "kind": "skill", "skill": "build/nextjs-enterprise-conventions",
          "inputs": { "target": "$repo", "baseline": "$profile.baselines.nextjs" }, "gate": true }
      ],
      "gate": { "kind": "exit", "step": "conventions" },
      "evidence": ["$steps.files:files.txt", "$steps.tests:test-plan.md", "$steps.tests:scaffold-report.json", "$steps.code:diff.patch", "$steps.code:agent-summary.md", "$steps.conventions:report.md"]
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
| `test-strategy-tdd` read `feature.md` and `plan.json#files` from the plan step | a `feature-from-plan` compose step derives `feature.md` (one criterion per task) from `tasks.csv`; `files` comes from the **files step** (`$steps.files:files.txt#csv`); output is `test-plan.md`, not `tests-report.md` | `spec-to-plan` writes `plan.md` + `tasks.csv` only, and a plan composed without a brief names no files — the first real run failed there with a "missing input" that looked like a gate failure |
| the architecture stage went spec → plan → approval, gate = the approval | spec → plan → **plan-refine** → approval, gate = `all` of five checks on the refined `tasks.csv` **and** the approval (see "The architecture stage") | the first real run (`--provider none`) produced a scaffold with every field `[TO BE BASELINED — owner: Tech lead]` and "no files named", and a person was able to approve it. A plan with no files, no acceptance criteria and no tests is not a plan: the architect (an agent, or a person on the IDE path) now fills it, and the gate refuses it before anyone is asked |
| the build stage went feature → tests → code | feature → **files** → tests → code → conventions (see "The build stage") | the files the change touches must be known before tests are scaffolded; when the plan names them the executor derives `files.txt`, otherwise the builder is asked for that list first (exit 4), never the tests skill |
| evaluate gate: review PASS + security exit | plus `perf` and `ui` exit gates | each of those skills exits 1 on new high findings — a verdict the stage must honour |
| handoff gate on `docs/HANDOFF.md` | `HANDOFF.md` in the step folder | the skill writes `{out}/HANDOFF.md`; `--write-to-repo` is not used by the pipeline |
| `$run.draft_only` did not exist | `product-spec-prd` and `security-review` get `draft_only=true` when the provider is `dry` or `none` | their model step cannot run without a provider; the script draft is then the final, labelled as such |

### References
| Reference | Resolves to |
|---|---|
| `$in.<name>` | a pipeline input |
| `$repo` | the working checkout of the target repository (a `path` input to skills) |
| `$profile.<key>` | a stack-profile fact (`flavour`, `framework`, `package_manager`, `test_runner`, `deploy_target`, `migrations_dir`, `baselines.<check>`); `baselines.<nextjs|perf|ui|debt>` resolves to the repo-recorded findings.csv when the profile has one, else to the baseline the executor captured before the code step (see Stack profile and baselines) |
| `$steps.<id>:<file>[#json.key]` | an output file of an earlier step (same syntax as playbooks); `#key.path` reads a key of a `.json` file |
| `$steps.<id>:<text file>#csv` / `#lines` | the non-blank, non-`#` lines of a text file such as `files.txt`, joined with commas / newlines (how `test-strategy-tdd` gets its comma-separated `files`) |
| `$run.id`, `$run.state`, `$run.draft_only` | the run id; the run's honest state line for the handoff; `true` when the provider is `dry` or `none` (skills with a model step take their script draft as final) |
| `$evidence` | the evidence bundle so far (`evidence/EVIDENCE.md`) |

A plain string that is not a reference is a literal. Only the executor's own values exist: a template cannot name an
arbitrary `$run.*` or `$profile.*` key (the validator rejects it).

### Step kinds
| Kind | Runs | Records |
|---|---|---|
| `skill` | a published library skill via `run_skill.py`; `gate: true` means exit 1 blocks the stage; an optional input that resolves to nothing is omitted; exit 2 (missing input) fails the stage with the input named | run.json, outputs, checks |
| `compose` | a deterministic derivation of a file a later skill needs from what earlier steps wrote (`brief-from-request`, `spec-from-prd`, `feature-from-plan` — implemented in `scripts/deliver.py`, nothing invented, unknowns left to the skills' TBD markers) | the declared `outputs` |
| `agent` | **code step** (no `produces`): a coding agent (`claude-code` first) on the checkout, constrained to the files `files.txt` lists (plus the test files the test plan names) and the plan. `--builder none` stops the run (exit 4, `needs_builder.json`) for a person or IDE agent; `--builder manual` records a diff supplied at `<out>/build/diff.patch` (or `--patch`). **files step** (`produces: ["files.txt"]`): the list of repo-relative files the change will create or modify — derived by the executor from the refined `tasks.csv` (every task names files once the plan passed its gate), else asked of the builder the same three ways (see "The build stage"). **plan-refine step** (`produces: ["plan.md", "tasks.csv"]`): the architect turns the spec-to-plan scaffold into a complete plan (see "The architecture stage"); skipped deterministically when the scaffold already is one | code: diff.patch, files-changed.json (files outside `files.txt` are flagged), agent-summary.md · files: files.txt, files.json (source, derived, create/modify against the checkout) · plan-refine: plan.md, tasks.csv, plan-refine.json (source, skipped, gaps) |
| `approval` | waits for a person holding the stage's role (portal) or the requester (IDE); on the CLI, `--approve-all` or an `--approvals approvals.json` file (`{"approvals": [{"step", "by", "note"}]}`) satisfies it, otherwise the run stops with exit 3 and `needs_approval.json` | approval.json: who, when, note |
| `pr` | on the checkout: branch `deliver/<run-id>`, the checkout's changes committed as `skills-factory[bot]`, `gh auth setup-git` when `GH_TOKEN` is set, push to `origin`, then `gh pr create --title <title> --body-file EVIDENCE.md` with cwd = the checkout; `--dry` writes `pr.json` with `{"dry": true}` and touches nothing | pr.json (number, url, head sha, committed_as) |

### Gate kinds
`output` (a check on a step's file, check vocabulary of `scripts/check_output.py`), `exit` (step exit code 0),
`approval`, `all` / `any` (combinations), `external` (recorded, satisfied outside the run, e.g. CI on the PR).

When a stage gate combines output checks with an approval (`all` of …), the output checks are evaluated **before the
approval step runs**: a stage whose outputs the gate would refuse fails at once (exit 1, the detail in `gate.json`) and
is never put in front of an approver — no `needs_approval.json`, no portal poll.

A step input that **no earlier step produced** is never a gate verdict: the executor stops with exit 2 and
`<out>/wiring_error.json` naming the stage, the step, the input and the reference that resolved to nothing (distinct
from `needs_input.json`, which is a missing *user* input). Fix the pipeline, start a new run.

### The architecture stage
`spec-to-plan` writes a **scaffold**: one task per spec bullet, every field the spec does not give marked
`[TO BE BASELINED — owner: Tech lead]`, never invented. With `repo: "$repo"` every file a task does name is checked
against the real checkout and marked modify / create ("Repo check", `repo_check` column). A scaffold is not a plan; the
stage runs, in order:

| Step | Kind | Takes | Produces | Who fills it |
|---|---|---|---|---|
| `spec` | compose `spec-from-prd` | `brief.json`, `prd-final.md`, the request | `spec.md` (bullets, with `accept/test/rollback/files` when the brief's `tasks` give them), `spec.json#section` | — |
| `plan` | skill `spec-to-plan` | `spec.md`, the section, the checkout | the scaffold `plan.md` + `tasks.csv` (`id,task,acceptance,test,rollback,files,size,repo_check`) | — |
| `plan-refine` | agent, `produces: ["plan.md", "tasks.csv"]` | the scaffold, `prd-final.md`, the request, the checkout | the **refined** `plan.md` + `tasks.csv`: file table filled, every task with acceptance, test, rollback and files (repo-relative, `create` / `modify` per the repo check), nothing invented beyond what the PRD and the request state; `plan-refine.json` (source, skipped, gaps) | **skipped deterministically** when the scaffold is already complete (no empty or TBD cell in `acceptance`, `test`, `files` — a brief whose `tasks` carry `accept`, `test`, `files` gets there): the scaffold is copied in as the plan and nobody is asked. Otherwise `--builder none` / `manual` stop with exit 4 and `needs_builder.json` (`role: architect`) naming both `expected` paths `<out>/evidence/02-architecture/plan-refine/{plan.md,tasks.csv}` (or the `alternative` `<out>/build/plan/`, where `--plan <dir>` copies to) with the format, the rule and the gaps; `--builder claude-code` prompts `claude -p` (scaffold, tasks.csv, PRD, request, stack profile, the gaps) to write both files |
| `plan-approval` | approval | the refined plan | `approval.json` | a person holding `ai-solution-architect` (portal), the requester (IDE), `--approve-all` / `--approvals` (CLI) |

The gate is `all` of five checks on the **refined** `tasks.csv` — `csv_rows:files!empty`, `csv_rows:acceptance!empty`,
`csv_rows:files!tbd`, `csv_rows:acceptance!tbd`, `csv_rows:test!tbd` (`!tbd`: no cell carries `[TO BE BASELINED`; never
skipped, in dry mode either) — and the approval. The five checks run before the approval step: a refined plan that still
has TBD cells or names no files fails the stage (exit 1) with the rows and columns named in `gate.json`, and is never put
in front of an approver. Everything downstream (`feature`, `files`, `code`) reads `$steps.plan-refine:…`, so the build
starts from the plan that passed, and the scaffold stays in the evidence as what the skill wrote.

### The build stage
The build stage runs, in order:

| Step | Kind | Takes | Produces | Builder |
|---|---|---|---|---|
| `feature` | compose `feature-from-plan` | `plan.md`, `tasks.csv`, `brief.json` | `feature.md` (one criterion per task), `feature.json` | — |
| `files` | agent, `produces: ["files.txt"]` | the refined `plan.md`, `tasks.csv`, the checkout | `files.txt` — one repo-relative path per line (source files to create or modify; `#` comments allowed), `files.json` | **derived by the executor** from the refined `tasks.csv` (header `# derived by deliver.py …`; the builder is not asked) — always, once the plan passed its gate, since every task then names files. The builder fallback stays for a pipeline without a `tasks.csv` (a composed `fix`): `--files <file>` is taken first when given; `--builder none` stops with exit 4 and `needs_builder.json` saying exactly what to write and where: `<out>/evidence/03-build/files/files.txt` (`expected`; or `<out>/build/files.txt`, where `--files <file>` copies to); `--builder manual` expects it at one of those paths (else the same stop); `--builder claude-code` prompts `claude -p` (plan, tasks.csv, stack profile) to write it, and fails the step if it does not |
| `tests` | skill `test-strategy-tdd` | `feature.md`, `files` = `$steps.files:files.txt#csv`, the checkout | `test-plan.md`, `scaffold-report.json`, red stubs on the checkout | — |
| `code` | agent | `plan.md`, `test-plan.md`, `files.txt`, the checkout | `diff.patch`, `files-changed.json`, `agent-summary.md` | constrained to the files in `files.txt` plus test files (`tests/`, `__tests__/`, `e2e/`); anything else is flagged `outside_plan`. `--builder none` → exit 4 (`<out>/build/diff.patch` expected, or `--patch`); `manual` → that diff recorded (applied to the dry copy under `--dry`); `claude-code` → `claude -p`, `git diff` captured |
| `conventions` | skill `nextjs-enterprise-conventions`, `gate: true` | the checkout, the baseline | `report.md` | — |

`--resume` picks up at the first incomplete step of the stage: after the architect drops the refined `plan.md` /
`tasks.csv` in place the run continues with `plan-approval`; after the builder drops `files.txt` in place the run
continues with `tests`, then stops again at `code` until the diff is there. A resume removes the `needs_*.json` it
answers. `greenfield-app` runs the same architecture and build stages (`project-bootstrap` names its files in
`bootstrap-report.json`; the refined `tasks.csv` is what `files.txt` derives from).

### Stack profile and baselines (`scripts/stack_profile.py <repo>` → `stack-profile.json`)
Read once, before stage 1, never guessed: `flavour` (ts|js), `framework` (nextjs|…), `package_manager`, `test_runner`
(vitest|jest|pytest|none), `e2e` (playwright|none), `deploy_target` (vercel|aws|azure|gcp|fly|railway|unknown),
`migrations_dir` (or null), `monorepo_root`, `baselines` (paths to recorded findings.csv per check when present:
`docs/baselines/<nextjs|perf|ui|debt>-findings.csv` in the repo, else null). Every fact carries its `evidence` (the file it
was read from); a missing or empty directory profiles as unknowns. `flavour` is `ts | js | python | unknown`.
Skills that write files must honour it; skills that lint read it for file selection.
A greenfield pipeline sets `"stack_profile": {"after": "bootstrap"}`: the profile is read after that stage, because
before it there is nothing to read.

**Brownfield baselines — the gate rule is "no NEW high findings from this change", never "the repository is clean".**
A repository with 77 pre-existing conventions findings must not fail a one-file feature on debt it did not add. So,
before the build stage's `code` step applies anything, the executor runs every baseline-accepting skill a later step
uses — `nextjs-enterprise-conventions` (`nextjs`), `perf-review-runner` (`perf`), `ui-component-quality` (`ui`),
`tech-debt-audit-runner` (`debt`) — against the untouched code (`--provider none`, deterministic) and stores
`<out>/evidence/00-baseline/<skill>/{findings.csv,report.md,run.json}` plus `00-baseline/baseline.json`.
`$profile.baselines.<check>` then resolves to that `findings.csv`, so the gate skill marks every pre-existing finding
`known` and fails only on `new` high findings; the gate detail names them (`NX5 app/api/orders/export/route.js:5`).

| Rule | Behaviour |
|---|---|
| Profile-recorded baseline wins | a check with `docs/baselines/<check>-findings.csv` in the repo is counted, not re-captured; its path is what the skill receives (the team's recorded debt is the contract) |
| Untouched code | the checkout when it is clean; `git archive HEAD` into `<out>/baseline-repo` when it is not (the tests step has scaffolded tests, or a manual diff was handed over in place), so the diff never leaks into its own baseline |
| Once per run | `baseline.json` is read back on `--resume`; the skills are not re-run on a checkout that now carries the change |
| `--no-baseline` | skips the capture; every finding is then `new` and pre-existing debt fails the gate (the old behaviour) |
| Greenfield | nothing to baseline: the repository is created by the run (`status: skipped` in `baseline.json`) |
| A skill that writes no findings.csv | recorded as `source: error` with the reason; that gate runs without a baseline |

`run.json` carries the same record under `baseline` (`status`, `target_source`, `checks.<check>: {skill, source
captured|profile|error, findings, high, path}`), and EVIDENCE.md a **Baseline** line — findings per check before the
change, linked to the captured `findings.csv` — above the stage table. Fixing recorded debt is its own PR: re-record
`docs/baselines/<check>-findings.csv` from the skill's findings.csv when it is paid down.

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
| IDE (Claude Code, Cursor) → MCP `deliver` | the same `scripts/deliver.py` on the developer's machine with `--run <id> --portal <url>` (the portal prints the command); evidence posted to the portal. **The architect fills the plan**: with `--builder none` the run stops at `plan-refine` (exit 4) and the IDE agent or the developer writes the refined `plan.md` / `tasks.csv` at the paths `needs_builder.json` names (or passes `--plan <dir>`), then `--resume` | approval in the portal or the terminal; merge on the PR |
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
    [--approve-all | --approvals approvals.json] [--patch diff.patch] [--files files.txt] [--plan DIR] [--dry] [--resume] [--run-id ID]
    [--no-baseline] [--run <portal run id> --portal <url> [--approval-timeout 3600] [--poll-interval 30]]   # SF_API_KEY in env
```

`--out` is required unless `--run` is given, when it defaults to `runs/<run id>` under giri-skills — the command the
portal prints (`deliverCommand`) therefore runs as printed. The pipeline is a path, a name under `pipelines/` or
`pipelines/composed/`, or — with `--run`/`--portal` — the composed pipeline the portal stored on the run (see
"When no template fits").

| Exit | Meaning |
|---|---|
| 0 | every stage passed |
| 1 | a gate or step failed — the evidence so far is in `<out>/evidence/` (including a refined plan the architecture gate refused: TBD cells or no files in `tasks.csv`, named in `gate.json`, before any approval was asked) |
| 2 | bad arguments, a missing pipeline input (`needs_input.json`), or a **pipeline wiring error** (`wiring_error.json`: a step input no earlier step produced — fix the pipeline, never a gate verdict) |
| 3 | waiting for an approval (`needs_approval.json`); re-run with `--resume` and `--approvals` |
| 4 | waiting for the builder or the architect (`needs_builder.json`, its `step` and `role` say which): `plan-refine` → the architect writes the refined `plan.md` and `tasks.csv` at the two `expected` paths (or passes `--plan <dir>`); `files` → write `files.txt` at `expected` (or pass `--files`); `code` → drop the diff at `<out>/build/diff.patch` (or pass `--patch`); re-run with `--resume` |

`--dry` works on a copy of the repo under `<out>/repo` (git-initialised with a fixed identity and date so the run is
reproducible; a manual diff is applied to that copy so the lint and review stages assess the change; nothing is pushed).
Without `--dry` the checkout is used in place and the `pr` step needs `gh`. `--resume` keeps every completed step of
the first incomplete stage and re-runs the rest. The run id is derived from pipeline + request + repo (plus a time
suffix outside `--dry`), so a dry run is deterministic apart from the timestamps in `run.json` and `gate.json`.

## When no template fits
A template fits when its `fits.stacks` meets the repository's stack and `fits.request_kinds` names the request. When
none does, a pipeline is **composed** from the catalog — deterministically, nothing invented:

```
python3 scripts/stack_profile.py <repo> --json stack-profile.json
python3 scripts/compose_pipeline.py --profile stack-profile.json --request-kind fix --explain --out pipelines/composed/fix-billing.json
python3 scripts/deliver.py fix-billing --repo <repo> --request "…" --out runs/x --builder claude-code --provider anthropic
```

| Rule | What it means |
|---|---|
| Request kind | `shared/request-kinds.json`: `feature` → requirements, architecture, build, evaluate, deploy, operate · `fix` → build, evaluate, deploy, operate · `hardening` and `migration` → architecture onwards · `greenfield` (alias `new-app`) → a `bootstrap` stage, then every stage, profile read after bootstrap. `--stages a,b,c` overrides the list; `--mode` overrides the kind's mode |
| Stack | The signal ids of `studio/lib/github/detect.ts` (`nextjs`, `react`, `typescript`, `supabase`, `python`, `vercel`, `github-actions`, `tests`, …) derived from the stack profile (`--profile`) or given (`--stacks nextjs,supabase` — greenfield names the intended stack) |
| Role | For each stage, the first role in `roles/` (by file name) whose `stages` lists it; none → error |
| Skill fits | A skill's `SKILL.md` may declare `metadata.fits: {stacks: [...], request_kinds: [...]}` (ids from `shared/request-kinds.json`; `any` matches every stack; absent = fits anything; `scripts/validate.py` checks it). Every `skills/build/*` skill declares one. A skill is chosen when the stage's role lists it, its fits match the stack and the kind, and every step it needs is in the pipeline |
| Wiring | The **step library** inside `compose_pipeline.py` (mirrored in `studio/lib/delivery/compose.ts`) is the shipped templates' wiring: the same compose derivations (`brief-from-request`, `spec-from-prd`, `feature-from-plan`), inputs, gates and evidence — the `plan-refine` agent step and its five `tasks.csv` checks included (a stage's gates are flattened into one `all`, as the templates write it). A compose step is added to the first stage that needs it (a `fix` carries `brief` and `spec` into build); the agent files and build steps take the refined `plan.md`, else the composed `spec.md`; an optional input whose step is absent is dropped; a required one that is absent rejects the skill. Role skills the library has no recipe for (inputs not derivable from earlier steps or the profile: `supabase-schema-rls`, `safe-fix`, the ai-platform skills, …) are listed as rejected with that reason |
| Dropped stages | A stage with no fitting skill is dropped and the pipeline's `description` and `composed.notes` say so (a Python repo keeps requirements, architecture and operate: the library has no Python build, review or deploy skill — that is the honest answer, not a pretended run) |
| Explain | `--explain` prints the decision table: stage → role → step → skill → chosen / rejected / dropped / note → why |

The composed file validates with `scripts/validate_pipelines.py` (so it is checked by `scripts/validate.py` whenever it
lives under `pipelines/composed/`) and runs with `scripts/deliver.py <name>` (looked up under `pipelines/`, then
`pipelines/composed/`) or `<path>`. For the JS/AWS fixture (`tests/fixtures/delivery-repo`) a `feature` composes to
exactly the `feature-delivery` template, stage for stage (`tests/test_compose_pipeline.py`).

**Portal.** Deliver → "No template fits? Compose one" picks a catalog repository (its synced stack signals) and a
request kind, shows the stages and the decision table, and starts a run with the composed pipeline. The run stores the
pipeline's JSON in `sf_delivery_runs.pipeline_spec` (migration 0024, additive); the executor, given the run's pipeline
name with `--run … --portal …`, finds no template of that name, fetches the run and uses `pipeline_spec` (saved as
`<out>/pipeline.json` for `--resume`) — so the command the portal prints and the GitHub executor both work unchanged.
The MCP tool `compose` ({repo | stack_profile, request_kind, mode}) returns the pipeline JSON and the decision table and
persists nothing. `studio/lib/delivery/compose.ts` is the pure port; `studio/tests/compose.test.ts` proves parity against
fixtures the Python script produced (`studio/tests/fixtures/compose/`, regenerated as its README says).

## Evidence bundle
`evidence/` in the run: `stack-profile.json`, `00-baseline/` (brownfield: `baseline.json` and, per baseline-accepting
skill a later step uses, `<skill>/findings.csv` + `report.md` taken from the untouched code before the `code` step —
see Stack profile and baselines), one folder per stage (`<nn>-<stage>/<step>/…` — every step's outputs
and run_skill log) with `gate.json` (`{verdict, kind, detail, role, approved_by, at}`; verdict `pass | fail |
recorded | pending`), and `EVIDENCE.md` — the table that goes into the PR body (relative links only, so the bundle
travels), preceded by the **Baseline** line (findings per check before the change, e.g. `nextjs: 77 finding(s), 12
high — [findings.csv](evidence/00-baseline/nextjs-enterprise-conventions/findings.csv)`). `<out>/run.json` records
the stages, steps, exit codes, durations, the `baseline` record and the sha256 of every evidence file (the baseline
files included):

| Stage | Role | Gate | Verdict | Evidence |
|---|---|---|---|---|

## Definition of done for the factory
1. Every request enters a pipeline (portal or IDE) and exits with artifacts and gate evidence.
2. Templates cover greenfield and brownfield; a stack profile drives every stage; composition covers the rest.
3. Roles own stages and approvals; the portal records who did what.
4. The executor opens a real PR on a real repo; CI on that PR is the deploy gate.
5. Everything above is tested: pipeline validation, a dry run of every template in CI, executor tests, portal tests.
