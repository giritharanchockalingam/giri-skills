---
name: program-raid-status
description: Program status from a RAID log (risks, actions, issues, decisions) and a milestone plan — use for any weekly or steerco status pack of a delivery program: "this week's steerco status", "what is red, what is late and who owns the fix", "status as of <date>", "what moved since last week's report", "gate the steerco pack: fail if the program is red / amber is acceptable", a plan whose milestones depend on each other (dependency cycle), or a RAID item with no owner (R3). Computes milestone slip and RAG, the critical path, RAID exposure and overdue days, and the overall RAG by a documented rule; writes status.csv, raid-actions.csv, status-report.md (mermaid critical path) and status.json as of a stated date (never today by default); unowned items stay TBD for the Program manager; --strict exits 1 when red. Not for starting a new app or repo (project-bootstrap), AI risk registers or compliance (ai-governance-risk), release gates (ai-release-plan) or effort estimates (effort-estimator).
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
The reply **is the status report** (or its skeleton), never only a request for files. Keep it short (about 900 tokens), tables over prose. The first two lines are always:
1. `**Overall RAG: RED | AMBER | GREEN | pending — <reason>**` (as of <YYYY-MM-DD>).
2. `Run: python3 -I scripts/raid_status.py --raid <raid.csv> --milestones <milestones.csv> --as-of <YYYY-MM-DD> [--thresholds …] [--previous status.json] [--strict] --out-dir out` → `status.csv`, `raid-actions.csv`, `status-report.md`, `status.json` (use the case's flags; `--verify <file> --as-of <date>` re-derives slip, RAG and overdue days).

**Never**
- Never assign an owner, even one the user names ("just put the platform lead on R3") and never infer one from a related item. A blank RAID or milestone owner (e.g. a milestone row whose owner cell is empty) stays `[TO BE BASELINED — owner: Program manager]` in every table. Say in one line "Not assigned: naming an owner is the Program manager's decision", and add a Decision needed `Name an owner for <id> — [TO BE BASELINED — owner: Program manager]` for each.
- Never assume today's date: no as-of date → ask once for it (YYYY-MM-DD), say "the system date will not be used"; the run **stops (exit 2)**.
- Never round a slip at the boundary: with defaults, slip 0 or less = green, slip 1–10 = **amber** (slip 10 is amber: 10 > 0 and 10 ≤ 10), slip 11+ = red. An amber milestone anywhere makes the overall at least **AMBER**, never GREEN.
- Never continue after a dependency cycle: the run **stops (exit 1)**, nothing is written, no RAG or critical path.

**Procedure — compute row by row from the supplied CSVs; never estimate** (`scripts/raid_status.py`, `references/method.md`)
1. Thresholds: supplied file, else green_max_slip_days 0, amber_max_slip_days 10, red_exposure 20.
2. Cycle check first: a `depends_on` loop (A depends on B and B on A) → "**stops (exit 1)**: dependency cycle among milestones: <ids>". Missing raid, milestones or as_of, a bad date, or a risk without likelihood/impact → "**stops (exit 2)**" naming the input.
3. Per milestone: slip_days = forecast_date − baseline_date in calendar days — across a month end, count the days left in the baseline month plus the day-of-month of the forecast (2026-09-20 → 2026-10-05 = 10 + 5 = 15); never eyeball it. Status `done` → `complete`. Else, in order: forecast_date < as_of → red (late); slip > amber_max → red; slip > green_max → amber; else green; `blocked` lifts green to amber.
4. Critical path: EF = duration_days + max EF of its `depends_on` (0 if none; tie → lowest id). End = largest EF (tie → lowest id); trace back through the predecessor with the largest EF. Write `M… → … = N days` (N = end EF).
5. RAID, open items only: exposure = likelihood × impact (issue with blank likelihood counts 5); overdue_days = max(0, as_of − due); age_days = as_of − raised. Top risks = open `risk` rows by exposure desc (tie → id), top 5.
6. Overall RAG, first rule that matches: **RED** if an open critical-path milestone is red, or an open item with exposure ≥ red_exposure has overdue_days > 0; else **AMBER** if any open milestone is amber or red, any open item is overdue, or any open item has a blank owner; else **GREEN**. State it as "Overall RAG rule: …" with the reason(s) that fired.
7. Gate (`--strict`): RED → "`--strict` was set: the run fails (exit 1) because overall RAG is red." (all outputs still written). AMBER or GREEN → "strict gate passed (exit 0)".
8. Previous `status.json` → **Since last report**, compared with ITS values, not the baseline:
   - overall RAG: its `overall_rag` → now (e.g. "stays red").
   - per milestone: moved = forecast now − its `milestones[].forecast` (days, +slipped / −pulled in); RAG its `rag` → now; done now but not complete then = `completed`. List every milestone that moved or changed RAG: `| id | change | +days | RAG before | RAG now |`.
   - RAID: closed = ids in its `raid_actions` that are not open now (e.g. status `closed` in this RAID log); opened = open now, absent then.
   - `End of the critical path (<end id>) moved from <its forecast for that id> to <forecast now>.`

**Reply layout after the two lines**
1. Working tables: milestones `id | baseline | forecast | slip | rule hit | RAG | EF | critical | owner`; open RAID `id | L | I | exposure | due | overdue | owner`.
2. **Summary** (rule and reasons, thresholds, gate line if strict), **Since last report** (when previous), **Critical path** (`… = N days` + a short mermaid `flowchart LR`), **Top risks** (top 5 by exposure), **Overdue items** (ageing 1–7, 8–30, 31+), **Decisions needed** (each with an owner or the Program manager TBD), **Method** (planned durations; no float or resource levelling).

**No RAID log or plan in the conversation**: line 1 `**Overall RAG: pending — RAID log, milestone plan and as-of date not supplied**`, line 2 as above, then one line each:
- **Overall RAG** will follow the documented rule: RED if an open critical-path milestone is red or an open item with exposure ≥ 20 is overdue; AMBER if any milestone is amber/red (slip 1–10 days amber, > 10 or past forecast red), any item is overdue or unowned; else GREEN.
- **What's red / what's late**: milestones by slip and RAG; overdue RAID items with days overdue.
- **Critical path**: the longest dependency chain, `M… → … = N days`.
- **Top 5 risks by exposure** (likelihood × impact) with owner and next action.
- **Who owns the fix**: owner per item; unowned items show `[TO BE BASELINED — owner: Program manager]`, never a guessed name.
- Ask once, one list: the as-of date (YYYY-MM-DD; today's date is not assumed), the RAID log (`assets/raid-template.csv`), the milestone plan (`assets/milestones-template.csv`).

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
