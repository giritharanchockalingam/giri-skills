---
name: ai-release-plan
description: Use when an AI/LLM feature is ready to ship and the user needs a staged rollout with go/no-go gates — "plan the release of our agent", "shadow and canary plan for the new model", "are we ready to roll out", "what are the rollback triggers". Produces release-plan.md (Readiness, Stages, Gates, Rollback, Owners) and gates.json from a release-facts CSV and an owner-supplied gates CSV - offline eval, shadow, canary steps sized by risk tier, GA; which gates are met now; minimum stage durations from traffic; rollback triggers; an owner per step. Gates are never defaulted. Not for building the eval set (llm-eval-harness), risk tiering (ai-governance-risk) or CI/CD pipelines (ci-cd-vercel-github).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: deploy
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: facts, type: csv, required: true, from: "release facts key,value (layout: assets/release-facts.csv) - system_name, risk_tier, measured metrics, daily_requests, min_observed_requests, rollback_time_min, owner_<role>; a rollout already under way adds current_stage and current_stage_observed_requests with live metric readings"}
      - {name: gates, type: csv, required: true, from: "owner-supplied gates stage,metric,min,max (layout: assets/release-gates.csv); never defaulted"}
    run:
      - {step: plan, kind: script, cmd: "python3 -I scripts/release_plan.py --facts {facts} --gates {gates} --out-dir {out}"}
    outputs:
      - {path: "{out}/release-plan.md", checks: [exists, sections:["Readiness","Stages","Gates","Rollback","Owners"], no_unowned_tbd, numbers_trace_to:"{out}/gates.json"]}
      - {path: "{out}/gates.json", checks: [exists, json, contains:"\"first_stage_ready\": true", contains:"\"rollback_triggers\""]}
    modes:
      new:      {case: agent-happy-path, bring: "your release facts and gate thresholds before the first rollout"}
      existing: {case: agent-mode-existing, bring: "live readings and current stage of a rollout under way"}
---

# AI Release Plan (staged rollout)

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-release-plan --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-release-plan`). Report the `run.json` results; do not hand-write the deliverables the script produces (`release-plan.md`, `gates.json`). A first-stage gate that is not met fails the run (exit 1) on purpose; the plan is still written so the blockers are visible.

## Starting points
- **New** — first rollout of a release: bring the release facts and the owner's gate thresholds; the skill builds offline eval → shadow → canary → GA, checks the first-stage gates now and sizes each stage.
- **Existing** — a rollout already under way: add `current_stage`, the requests observed there and the live metric readings; the plan shows where you are and decides PROMOTE, HOLD or ROLL BACK for the current stage against the same gates.

## When to use
- A model, prompt, agent or RAG change is about to reach users and needs shadow → canary → GA with explicit gates.
- "Are we ready?" — evaluate the owner's gates against the measured facts now.
- NOT for: building the eval set or scoring it (`llm-eval-harness`), risk tiering (`ai-governance-risk`), pipeline wiring (`ci-cd-vercel-github`), live monitoring after GA (`llm-observability`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `facts` CSV `key,value`: `system_name`, `risk_tier` (low/medium/high) | yes | release owner; tier from `ai-governance-risk` |
| Measured metrics named by gates (e.g. `eval_pass_rate`, `redteam_pass_rate`, `latency_p95_ms`, `error_rate`) | for gate status | eval run, red-team run, staging telemetry |
| `daily_requests`, `min_observed_requests` | for durations | traffic forecast; owner's confidence target |
| `rollback_time_min`, `owner_<role>` (eval_lead, sre_oncall, release_manager, product_owner) | no | owner; missing → `[TO BE BASELINED — owner: Release manager]` |
| `current_stage` (stage id, e.g. `canary_1`), `current_stage_observed_requests` | only for a rollout under way | release manager; live telemetry — metric facts are then the live readings |
| `gates` CSV `stage,metric,min,max` (stage ∈ offline_eval, shadow, canary, ga) | yes | release owner — the skill never supplies a threshold |

If `facts` or `gates` is missing the runner exits 2 and asks once. Missing optional facts stay TBD with an owner role; nothing is invented.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Copy `assets/release-facts.csv` and `assets/release-gates.csv`; the owner fills measured values and thresholds (with sources).
3. Run the skill. The script builds the stage list from `references/rollout-policy.md` (canary steps by risk tier — the skill's policy, owner-overridable via `canary_steps`).
4. It evaluates every gate against the facts now (`references/gate-method.md`): met / NOT MET / not measured; `not measured` never counts as met.
5. It computes minimum shadow/canary durations: `ceil(min_observed_requests ÷ (daily_requests × traffic% ÷ 24))` hours.
6. It turns every live-stage gate into a rollback trigger and assigns an owner per step.
7. Exit 1 if any `offline_eval` gate is not met or none was supplied; report the blockers, do not soften them.
   With `current_stage` set it also decides the current stage: ROLL BACK (a gate not met now; exit 1), HOLD (a gate not measured, no gate, or too few requests observed) or PROMOTE to the next stage (COMPLETE at GA).
8. Run the self-check.

## Output
- `release-plan.md`: Readiness, Stages (traffic %, served, min hours, owner), Gates (threshold, actual now, status, source), Rollback (owner, time, triggers), Owners.
- `gates.json`: the same plan, machine-readable (`first_stage_ready`, `stages`, `gates`, `rollback_triggers`, `owners`, `current` — null unless a rollout is under way).

## Self-check
- [ ] Every gate threshold came from the gates CSV; none defaulted
- [ ] `not measured` gates are shown as such, never as met
- [ ] Canary steps state their basis (tier policy or owner override)
- [ ] Durations trace to `daily_requests` and `min_observed_requests`, or are TBD with an owner
- [ ] Every rollback trigger maps to a gate; rollback owner named or TBD with role
- [ ] Exit 1 when the first stage is blocked

## References
- `references/rollout-policy.md` — stage sequence, canary steps per risk tier (skill policy), owner per step
- `references/gate-method.md` — gate statuses, duration formula, rollback triggers
- `assets/release-facts.csv`, `assets/release-gates.csv` — input layouts
- `scripts/release_plan.py` — the planner (argparse; stdlib)
