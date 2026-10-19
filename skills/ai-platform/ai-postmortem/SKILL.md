---
name: ai-postmortem
description: Use after an AI incident is contained and the team needs to learn from it — "write the postmortem for the billing bot incident", "blameless postmortem for the prompt injection", "how long did it take us to detect and mitigate", "turn this incident into regression evals". Produces postmortem.md (Summary, Impact, Timeline, Timings, Contributing factors, What went well, Actions, Lessons for the eval set, Method), timings.json, actions.csv and eval-cases.csv from incident facts, a timeline and optional factors and actions - measured time to detect, acknowledge, mitigate and resolve; missing or out-of-order milestones flagged, never invented; AI factor taxonomy; factor-to-action coverage; owner TBDs; a blame-phrasing check; regression cases in llm-eval-harness golden-set columns. --strict exits 1 when a factor has no action or an action has no owner. Not for responding during a live incident (use ai-incident-runbook), alerting (llm-observability) or scoring evals (llm-eval-harness).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: improve
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: incident, type: csv, required: true, from: "incident facts key,value,source,notes (layout: assets/incident-template.csv) - id, title, started_at required; severity SEV1-4, system, customer_impact, detection_source, went_well optional"}
      - {name: timeline, type: csv, required: true, from: "timestamp,event,description,actor_role (layout: assets/timeline-template.csv); event detected|acknowledged|mitigated|resolved|note|change; ISO 8601 with timezone"}
      - {name: factors, type: csv, required: false, from: "factor,category,evidence (layout: assets/factors-template.csv; category from assets/factor-taxonomy.csv); without it factors are TBD for the Incident commander"}
      - {name: actions, type: csv, required: false, from: "action,type,owner,due,factor (layout: assets/actions-template.csv; type prevent|detect|mitigate|process); without it actions are TBD for the Incident commander"}
      - {name: strict, type: flag, required: false, flag: "--strict", from: "true to fail the run (exit 1) when a factor has no action, an action has no owner, or no factors were supplied"}
    run:
      - {step: postmortem, kind: script, cmd: "python3 -I scripts/postmortem.py --incident {incident} --timeline {timeline} [--factors {factors}] [--actions {actions}] {strict} --out-dir {out}"}
    outputs:
      - {path: "{out}/postmortem.md", checks: [exists, sections:["Summary","Impact","Timeline","Timings","Contributing factors","What went well","Actions","Lessons for the eval set","Method"], no_unowned_tbd, cmd:"python3 -I scripts/postmortem.py --verify {path}"]}
      - {path: "{out}/timings.json", checks: [exists, json, contains:"\"timings_min\"", contains:"\"strict_gate\"", cmd:"python3 -I scripts/postmortem.py --verify {path}"]}
      - {path: "{out}/actions.csv", checks: [exists, csv:[action,type,owner,due,factor,status], no_unowned_tbd, cmd:"python3 -I scripts/postmortem.py --verify {path}"]}
      - {path: "{out}/eval-cases.csv", checks: [exists, csv:[id,category,difficulty,input,expected,must_contain,must_not_contain,expected_json_valid,weight,source,notes], no_unowned_tbd, cmd:"python3 -I scripts/postmortem.py --verify {path}"]}
    modes:
      existing: {case: agent-happy-path, bring: "the incident facts and timeline from an incident that happened"}
---

# AI Postmortem (blameless, measured, owned)

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-postmortem --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-postmortem`). Report the `run.json` results; do not hand-write the deliverables the script produces (`postmortem.md`, `timings.json`, `actions.csv`, `eval-cases.csv`). With `strict=true` the run is a gate: it exits 1 when a factor has no action or an action has no owner, and still writes every output so the gaps are visible.

## Starting points
- **Existing** — you bring the facts and timeline of an incident that happened (plus factors and actions when known); the skill measures the timings, checks the actions cover every factor and turns the failure into eval cases.
- Only for existing: a postmortem always concerns an incident that has already happened; a live incident goes to `ai-incident-runbook`.

## When to use
- After an AI incident is mitigated: bad answers at scale, prompt-injection exploit, cost runaway, outage, harmful output, data leak.
- Measuring time to detect, acknowledge, mitigate and resolve from the real timeline, and showing which milestones are missing.
- Closing the loop: every contributing factor has an owned, dated action; failing inputs become regression evals.
- NOT for: responding while the incident is live — severity, containment, comms (`ai-incident-runbook`); alerts and SLOs (`llm-observability`); scoring the eval set (`llm-eval-harness`); legal or HR determinations.

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `incident` — `key,value,source,notes`: `id`, `title`, `started_at` (+ `severity`, `system`, `customer_impact`, `detection_source`, `went_well`) | yes | Incident commander; severity and start time from the `ai-incident-runbook` run | run stops (exit 2), asks once; optional keys become `[TO BE BASELINED — owner: Incident commander]` |
| `timeline` — `timestamp,event,description,actor_role` | yes | incident channel, pager, deploy log | run stops (exit 2), asks once |
| `factors` — `factor,category,evidence` | no | postmortem review meeting | factors TBD for the Incident commander; strict gate fails |
| `actions` — `action,type,owner,due,factor` | no | postmortem review meeting | actions TBD for the Incident commander |
| `strict` — true/false | no | engineering lead | false: gaps reported, run exits 0 |

Write `actor_role` as a role, never a person's name. Mark a failing user input in any description or evidence as `input:"..."` and the bad reply as `output:"..."` so it can become a regression case.

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md`.
2. Copy `assets/incident-template.csv`, `assets/timeline-template.csv`, `assets/factors-template.csv` and `assets/actions-template.csv`. Carry `started_at`, `detected_at` and severity over from the `ai-incident-runbook` output.
3. Pick each factor's category from `assets/factor-taxonomy.csv`. Describe systems and processes, not people.
4. Run the skill. `scripts/postmortem.py` computes timings per `references/method.md`, flags missing and out-of-order milestones, links actions to factors and scans for blame phrasing (`assets/blame-phrases.csv`).
5. Fix every flag in the inputs (rewrite blameful text, add owners, link uncovered factors) and re-run until the strict gate passes.
6. Hand `eval-cases.csv` to the Eval lead: fill `must_contain` / `must_not_contain`, then feed it to `llm-eval-harness`.
7. Run the self-check.

## Output
- `postmortem.md` — **Summary**, **Impact**, **Timeline**, **Timings**, **Contributing factors**, **What went well**, **Actions**, **Lessons for the eval set**, **Method** (with the blameless language check).
- `timings.json` — milestones, minutes per measure with basis, flags, coverage and gate result.
- `actions.csv` — `action, type, owner, due, factor, status` (status `open | in-progress | done | blocked: no owner | blocked: no due date`).
- `eval-cases.csv` — proposed regression cases in the `llm-eval-harness` golden-set columns.

## Self-check
- [ ] Every timing traces to two timeline timestamps; missing milestones are flagged, not estimated
- [ ] An incident with no `resolved` event is reported OPEN
- [ ] Every factor has at least one action; every action has an owner and a due date, or a TBD naming the Incident commander
- [ ] Blame-phrase hits rewritten as system or process conditions
- [ ] Eval cases use only inputs quoted in the timeline or factors; scoring left to the Eval lead
- [ ] `--verify` passes on all four outputs
- [ ] Limits stated: word-list blame scan, timeline accuracy, not a legal determination

## References
- `references/method.md` — timing definitions, ordering rules, coverage, eval-case extraction, limits
- `references/sources.md` — blameless postmortem practice (Google SRE book ch. 15, SRE workbook ch. 10), checked 2026-10-18
- `assets/factor-taxonomy.csv` — AI contributing-factor categories
- `assets/blame-phrases.csv` — blame word list with rewrite hints
- `assets/incident-template.csv`, `assets/timeline-template.csv`, `assets/factors-template.csv`, `assets/actions-template.csv` — input layouts
- `scripts/postmortem.py` — builder and `--verify` (argparse; stdlib)
