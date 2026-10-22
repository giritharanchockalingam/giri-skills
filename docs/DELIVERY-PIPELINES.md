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

```jsonc
{
  "name": "feature-delivery",
  "version": "0.1.0",
  "title": "Feature delivery on an existing application",
  "description": "Brownfield: a feature request on a repository the catalog knows, through requirements, architecture, build, evaluate, deploy and operate.",
  "mode": "brownfield",                       // brownfield | greenfield
  "fits": { "stacks": ["nextjs"], "request_kinds": ["feature", "fix", "hardening"] },
  "inputs": [
    { "name": "repo",    "type": "repo",   "required": true,  "from": "catalog repository (owner/name) or a local checkout" },
    { "name": "ref",     "type": "string", "required": false, "from": "branch or commit to start from (default: default branch)" },
    { "name": "request", "type": "text",   "required": true,  "from": "the feature request in the requester's words, or a path to a brief" },
    { "name": "brief",   "type": "json",   "required": false, "from": "product brief for product-spec-prd (layout: skills/build/product-spec-prd/assets/brief-template.json)" }
  ],
  "stack_profile": { "from": "repo", "detect": "scripts/stack_profile.py" },
  "stages": [
    {
      "id": "requirements", "adlc_stage": "requirements", "role": "ai-product-manager",
      "steps": [
        { "id": "prd", "kind": "skill", "skill": "build/product-spec-prd", "inputs": { "brief": "$in.brief", "request": "$in.request" } }
      ],
      "gate": { "kind": "output", "step": "prd", "file": "prd.md", "check": "sections:[\"Acceptance criteria\"]" },
      "evidence": ["$steps.prd:prd.md"]
    },
    {
      "id": "architecture", "adlc_stage": "architecture", "role": "ai-solution-architect",
      "steps": [
        { "id": "plan", "kind": "skill", "skill": "build/spec-to-plan", "inputs": { "spec": "$steps.prd:prd.md", "section": "$in.request" } },
        { "id": "plan-approval", "kind": "approval", "role": "ai-solution-architect", "note": "Approve the plan before any code is written" }
      ],
      "gate": { "kind": "approval", "step": "plan-approval" },
      "evidence": ["$steps.plan:plan.md"]
    },
    {
      "id": "build", "adlc_stage": "build", "role": "full-stack-engineer",
      "steps": [
        { "id": "tests", "kind": "skill", "skill": "build/test-strategy-tdd", "inputs": { "feature": "$steps.plan:feature.md", "files": "$steps.plan:plan.json#files", "target": "$repo" } },
        { "id": "code",  "kind": "agent", "agent": "claude-code", "inputs": { "plan": "$steps.plan:plan.md", "tests": "$steps.tests:tests-report.md", "target": "$repo" },
          "constraints": ["skills/build/nextjs-enterprise-conventions/SKILL.md", "shared/stack-conventions.md"] },
        { "id": "conventions", "kind": "skill", "skill": "build/nextjs-enterprise-conventions", "inputs": { "target": "$repo", "baseline": "$profile.baselines.nextjs" }, "gate": true }
      ],
      "gate": { "kind": "exit", "step": "conventions" },
      "evidence": ["$steps.tests:tests-report.md", "$steps.code:diff.patch", "$steps.conventions:report.md"]
    },
    {
      "id": "evaluate", "adlc_stage": "evaluate", "role": "ai-quality-red-team",
      "steps": [
        { "id": "review",   "kind": "skill", "skill": "build/code-review-runner", "inputs": { "diff": "$steps.code:diff.patch", "spec": "$steps.prd:prd.md" } },
        { "id": "security", "kind": "skill", "skill": "build/security-review",   "inputs": { "diff": "$steps.code:diff.patch" } },
        { "id": "perf",     "kind": "skill", "skill": "build/perf-review-runner", "inputs": { "target": "$repo", "baseline": "$profile.baselines.perf" } },
        { "id": "ui",       "kind": "skill", "skill": "build/ui-component-quality", "inputs": { "target": "$repo", "baseline": "$profile.baselines.ui" } }
      ],
      "gate": { "kind": "all", "of": [ { "kind": "output", "step": "review", "file": "review.md", "check": "contains:\"Verdict: **PASS**\"" }, { "kind": "exit", "step": "security" } ] },
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
      "steps": [ { "id": "handoff", "kind": "skill", "skill": "build/handoff-and-thread-close", "inputs": { "target": "$repo", "state": "$run.state" } } ],
      "gate": { "kind": "output", "step": "handoff", "file": "docs/HANDOFF.md", "check": "exists" },
      "evidence": ["$steps.handoff:docs/HANDOFF.md"]
    }
  ],
  "outputs": ["$steps.pr:pr.json", "$evidence"]
}
```

### References
| Reference | Resolves to |
|---|---|
| `$in.<name>` | a pipeline input |
| `$repo` | the working checkout of the target repository (a `path` input to skills) |
| `$profile.<key>` | a stack-profile fact (`flavour`, `framework`, `package_manager`, `test_runner`, `deploy_target`, `migrations_dir`, `baselines.<check>`) |
| `$steps.<id>:<file>[#json.key]` | an output file of an earlier step (same syntax as playbooks) |
| `$run.id`, `$run.state` | the run id; the run's honest state line for the handoff |
| `$evidence` | the evidence bundle so far (Markdown) |

### Step kinds
| Kind | Runs | Records |
|---|---|---|
| `skill` | a published library skill via `run_skill.py`; `gate: true` means exit 1 blocks the stage | run.json, outputs, checks |
| `agent` | a coding agent (`claude-code` first) on the checkout, constrained by the listed files and the plan; it may only touch files the plan names | diff.patch, files changed, the agent's own summary |
| `approval` | waits for a person holding the stage's role (portal) or the requester (IDE) | who, when, note |
| `pr` | opens the pull request on the target repo with the evidence bundle | pr.json (number, url, head sha) |

### Gate kinds
`output` (a check on a step's file, check vocabulary of `scripts/check_output.py`), `exit` (step exit code 0),
`approval`, `all` / `any` (combinations), `external` (recorded, satisfied outside the run, e.g. CI on the PR).

### Stack profile (`scripts/stack_profile.py <repo>` → `stack-profile.json`)
Read once, before stage 1, never guessed: `flavour` (ts|js), `framework` (nextjs|…), `package_manager`, `test_runner`
(vitest|jest|pytest|none), `e2e` (playwright|none), `deploy_target` (vercel|aws|azure|gcp|fly|railway|unknown),
`migrations_dir` (or null), `monorepo_root`, `baselines` (paths to recorded findings.csv per check when present).
Skills that write files must honour it; skills that lint read it for file selection.

## Roles own stages
`roles/<role>.json` gains `"stages": ["requirements", …]` — the ADLC stages the role may own. A pipeline validates
that every stage's role lists that stage and that the role's `skills` include every skill the stage runs. At run time
the portal checks `sf_pipeline_access` (who may start the pipeline) and records the owning role per stage in the
evidence; an approval step is satisfied only by a member assigned to the stage's role.

## Where it runs
| Entry | Executor | Human gates |
|---|---|---|
| Portal → Deliver | GitHub Actions `delivery.yml` in giri-skills, dispatched with repo, ref, request, pipeline | approval in the portal; merge on the PR |
| IDE (Claude Code, Cursor) → MCP `deliver` | the same `scripts/deliver.py` on the developer's machine; evidence posted to the portal | approval in the terminal; merge on the PR |
| CI (`deliver.py --dry`) | every pipeline template dry-runs on a fixture repo on each PR to this library | none |

## When no template fits
`scripts/compose_pipeline.py --stack <profile> --request-kind <kind>` assembles a pipeline from the catalog: one
stage per ADLC stage the request kind needs, the role whose `stages` lists it, the role's skills whose `fits`
matches the stack. The composed file is saved under `pipelines/composed/` and validated like any template.

## Evidence bundle
`evidence/` in the run: `stack-profile.json`, one folder per stage with the step outputs and `gate.json`
(`{verdict, kind, detail, role, approved_by, at}`), and `EVIDENCE.md` — the table that goes into the PR body:

| Stage | Role | Gate | Verdict | Evidence |
|---|---|---|---|---|

## Definition of done for the factory
1. Every request enters a pipeline (portal or IDE) and exits with artifacts and gate evidence.
2. Templates cover greenfield and brownfield; a stack profile drives every stage; composition covers the rest.
3. Roles own stages and approvals; the portal records who did what.
4. The executor opens a real PR on a real repo; CI on that PR is the deploy gate.
5. Everything above is tested: pipeline validation, a dry run of every template in CI, executor tests, portal tests.
