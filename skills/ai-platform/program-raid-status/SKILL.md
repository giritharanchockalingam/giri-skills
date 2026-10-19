---
name: program-raid-status
description: Use when the user asks for the status of an AI delivery program from its RAID log and milestone plan — "program status report", "what is red and what is late", "critical path for the pilot", "RAID review", "top risks and overdue actions", "steerco status". Produces status.csv (milestone slip, RAG, critical path), raid-actions.csv (exposure, owner, overdue days, next action), status-report.md (Summary with the overall RAG rule, Milestones, Critical path with a mermaid flowchart, Top risks, Overdue items, Decisions needed, Method) and status.json, as of a stated date (never today's date by default). Unowned items become TBD for the Program manager. Gate: --strict exits 1 when the overall RAG is red. Not for building an AI risk register or compliance review (use ai-governance-risk), staged release gates (use ai-release-plan) or effort estimates (use effort-estimator).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: build
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: raid, type: csv, required: true, from: "RAID log id,type,description,owner,likelihood,impact,due,status,mitigation[,raised] (layout: assets/raid-template.csv)"}
      - {name: milestones, type: csv, required: true, from: "id,milestone,baseline_date,forecast_date,duration_days,depends_on,status[,owner] (layout: assets/milestones-template.csv; depends_on '|'-separated ids)"}
      - {name: as_of, type: string, required: true, from: "status date YYYY-MM-DD (never defaulted to today)"}
      - {name: thresholds, type: csv, required: false, from: "key,value RAG thresholds green_max_slip_days, amber_max_slip_days, red_exposure (default: assets/thresholds.csv values)"}
      - {name: strict, type: flag, required: false, flag: "--strict", from: "true to fail the run (exit 1) when the overall RAG is red"}
    run:
      - {step: status, kind: script, cmd: "python3 -I scripts/raid_status.py --raid {raid} --milestones {milestones} --as-of {as_of} [--thresholds {thresholds}] {strict} --out-dir {out}"}
    outputs:
      - {path: "{out}/status.csv", checks: [exists, csv:[milestone,baseline,forecast,slip_days,rag,on_critical_path], "csv_rows:rag~^(red|amber|green|complete)$", "csv_rows:slip_days~^-?\\d+$", cmd:"python3 -I scripts/raid_status.py --verify {path} --as-of {as_of}"]}
      - {path: "{out}/raid-actions.csv", checks: [exists, csv:[id,type,exposure,owner,due,overdue_days,next_action], csv_rows:owner!empty, csv_rows:next_action!empty, cmd:"python3 -I scripts/raid_status.py --verify {path} --as-of {as_of}"]}
      - {path: "{out}/status-report.md", checks: [exists, sections:["Summary","Milestones","Critical path","Top risks","Overdue items","Decisions needed","Method"], no_unowned_tbd, mermaid_parses, contains:"Overall RAG rule"]}
---

# Program RAID Status

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/program-raid-status --input <name>=<value> … --out <dir>` (see `--explain ai-platform/program-raid-status`). Report the `run.json` results; do not hand-write the deliverables the script produces (`status.csv`, `raid-actions.csv`, `status-report.md`, `status.json`). `--verify` re-derives slip, RAG bounds and overdue days from the CSVs.

## When to use
- ADLC build stage: weekly or steerco status for an AI delivery program (pilot, platform, agent rollout).
- "What is red, what is late, what is on the critical path, and who owns the fix?"
- Gate a status pack: `strict=true` fails the run when the overall RAG is red.
- NOT for: AI risk registers or compliance reviews (`ai-governance-risk`), release go/no-go gates (`ai-release-plan`), effort or cost estimates (`effort-estimator`), resource-levelled scheduling.

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `raid` — RAID log CSV | yes | Program manager (copy `assets/raid-template.csv`) | run stops (exit 2), asks once |
| `milestones` — milestone plan CSV | yes | Program manager (copy `assets/milestones-template.csv`) | run stops (exit 2), asks once |
| `as_of` — status date YYYY-MM-DD | yes | Program manager | run stops (exit 2); never defaults to today |
| `thresholds` — key,value | no | PMO (copy `assets/thresholds.csv`) | skill defaults: green ≤ 0, amber ≤ 10 days slip, red exposure ≥ 20 |
| `strict` — true/false | no | PMO | false: RAG reported, exit 0 |

Blank RAID or milestone owners become `[TO BE BASELINED — owner: Program manager]`.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Confirm the RAID log and forecasts were updated for this period, and agree the `as_of` date.
3. Run the agent. `scripts/raid_status.py` computes slip and RAG per milestone, the critical path through `depends_on`, exposure and overdue days per RAID item, and the overall RAG by the rule in `references/method.md`.
4. A dependency cycle stops the run (exit 1) and names the milestones; fix the plan and rerun.
5. Review "Decisions needed" with the sponsor; every decision names an owner or a TBD for the Program manager.
6. Run the self-check.

## Output
- `status.csv` — `id, milestone, baseline, forecast, slip_days, rag, on_critical_path, status`.
- `raid-actions.csv` — open items: `id, type, exposure, owner, due, overdue_days, age_days, next_action`.
- `status-report.md` — **Summary** (overall RAG and the rule), **Milestones**, **Critical path** (mermaid flowchart), **Top risks** (top 5 by exposure), **Overdue items** (with ageing), **Decisions needed**, **Method**.
- `status.json` — the same, machine-readable.

## Self-check
- [ ] The `as_of` date was supplied, not assumed
- [ ] Both CSVs pass `--verify`
- [ ] Every open item has an owner or a TBD for the Program manager
- [ ] The overall RAG matches the documented rule; thresholds stated
- [ ] Limits stated: planned durations, no float or resource levelling

## References
- `references/method.md` — RAG thresholds, critical-path method, exposure, overall RAG rule
- `assets/raid-template.csv`, `assets/milestones-template.csv`, `assets/thresholds.csv` — input layouts and default thresholds
- `scripts/raid_status.py` — status builder and `--verify` (argparse; stdlib)
