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
      - {name: previous, type: json, required: false, from: "status.json of the last report; adds Since last report (forecast moves, RAG changes, completions, RAID opened/closed, end-date movement)"}
    run:
      - {step: status, kind: script, cmd: "python3 -I scripts/raid_status.py --raid {raid} --milestones {milestones} --as-of {as_of} [--thresholds {thresholds}] [--previous {previous}] {strict} --out-dir {out}"}
    outputs:
      - {path: "{out}/status.csv", checks: [exists, csv:[milestone,baseline,forecast,slip_days,rag,on_critical_path], "csv_rows:rag~^(red|amber|green|complete)$", "csv_rows:slip_days~^-?\\d+$", cmd:"python3 -I scripts/raid_status.py --verify {path} --as-of {as_of}"]}
      - {path: "{out}/raid-actions.csv", checks: [exists, csv:[id,type,exposure,owner,due,overdue_days,next_action], cmd:"python3 -I scripts/raid_status.py --verify {path} --as-of {as_of}"]}
      - {path: "{out}/status-report.md", checks: [exists, sections:["Summary","Milestones","Critical path","Top risks","Overdue items","Decisions needed","Method"], no_unowned_tbd, mermaid_parses, contains:"Overall RAG rule"]}
    modes:
      new:      {case: agent-happy-path, bring: "your RAID log and milestone plan for a first status report"}
      existing: {case: agent-mode-existing, bring: "this week's RAID log and plan plus last report's status file"}
---

# Program RAID Status

## In a conversation: write the status now
**Never**
- Never assume today's date: no as-of date → ask for it (YYYY-MM-DD) and say "the system date will not be used".
- Never assign an owner the user names ("just put the platform lead on R3"): the owner stays `[TO BE BASELINED — owner: Program manager]` and a Decision needed reads "Name an owner for R3 — [TO BE BASELINED — owner: Program manager]". A blank milestone owner (e.g. M7) is also that TBD.
- Never call a milestone green when slip_days > green_max (default 0); slip 1–10 is **amber**, slip > 10 is **red**. Never report overall AMBER/GREEN when an open critical-path milestone is red — that is **RED**.
- Never continue after a dependency cycle: the run **stops (exit 1)**, nothing is written, no RAG or critical path is reported.

**Procedure (compute row by row from the supplied CSVs; never estimate)** — rules are `scripts/raid_status.py` / `references/method.md`:
1. Thresholds: supplied `thresholds` CSV, else green_max_slip_days 0, amber_max_slip_days 10, red_exposure 20.
2. Cycle check first: if `depends_on` forms a loop (e.g. M2 depends on M3 and M3 on M2), say "**stops (exit 1)**: dependency cycle among milestones: M2, M3" and stop. Missing raid, milestones or as_of, a bad date, or a risk without likelihood/impact → "**stops (exit 2)**" naming the input.
3. Per milestone: slip_days = forecast_date − baseline_date (calendar days). status `done` → `complete`. Else: forecast_date < as_of → red (late); slip > amber_max → red; slip > green_max → amber; else green; `blocked` lifts green to amber.
4. Critical path: earliest finish EF = duration_days + max EF of its `depends_on` (0 if none; ties → lowest id). End = largest EF (tie → lowest id); trace back through the predecessor with the largest EF. Path length = end EF in days. Zero-float milestones are also on_critical_path = yes.
5. RAID (open items only): exposure = likelihood × impact; an issue with blank likelihood counts 5. overdue_days = max(0, as_of − due); age_days = as_of − raised. Top risks = open `risk` rows by exposure desc (tie → id), top 5.
6. Overall RAG — apply in order: **RED** if any open critical-path milestone is red, or any open item with exposure ≥ red_exposure has overdue_days > 0; else **AMBER** if any open milestone is amber/red, any open item is overdue, or any open item has a blank owner; else **GREEN**.
7. Gate (`strict`): RED → "`--strict` was set: the run fails (exit 1) because overall RAG is red." — every output is still written. AMBER/GREEN → "gate passed", exit 0.

**Reply layout**: first the working tables — milestones (id, baseline, forecast, slip_days, rule hit, RAG, EF, on_critical_path) and open RAID (id, L, I, exposure, due, overdue_days, owner) — then the verdict, then `status-report.md` sections: **Summary** ("**Overall RAG: RED**" + the reasons + the line "Overall RAG rule: …" + thresholds), **Milestones**, **Critical path** ("M1 → M2 → … = N days" + mermaid flowchart), **Top risks**, **Overdue items** (with ageing buckets 1–7, 8–30, 31+), **Decisions needed** (each with an owner or the TBD), **Method**.
- Name the run: `python3 -I scripts/raid_status.py --raid <raid.csv> --milestones <milestones.csv> --as-of <YYYY-MM-DD> [--thresholds …] [--previous status.json] [--strict] --out-dir <dir>`; outputs `status.csv`, `raid-actions.csv`, `status-report.md`, `status.json`; `--verify <file> --as-of <date>` re-derives slip, RAG and overdue days.
- **Files not attached** (a request with no data): still name the run above and the reported content — overall RAG with the documented rule, the critical path and the top 5 risks by exposure; say unowned items show `[TO BE BASELINED — owner: Program manager]`; ask once, in one list, for the as-of date, the RAID log (`assets/raid-template.csv`) and the milestone plan (`assets/milestones-template.csv`).
- **Last report given** (`previous`): add "Since last report" — overall RAG then → now, per milestone forecast moved (days, +slipped/−pulled in) and RAG before → now, completions, RAID opened/closed (ids open now vs then), and the end of the critical path moved from → to.

## Starting points
- **New** — the first status report for a program: RAG, critical path, top risks, overdue items and decisions from the RAID log and milestone plan.
- **Existing** — also pass last report's `status.json` as `previous`: the report adds "Since last report" (overall RAG then and now, forecast moves and RAG changes per milestone, completions, RAID items opened and closed, end-date movement).

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

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/program-raid-status --input <name>=<value> … --out <dir>` (see `--explain ai-platform/program-raid-status`). Report the `run.json` results; do not hand-write the deliverables the script produces (`status.csv`, `raid-actions.csv`, `status-report.md`, `status.json`). `--verify` re-derives slip, RAG bounds and overdue days from the CSVs.
