---
name: ai-adoption-and-literacy
description: Use when the user asks how people will learn and adopt an AI system or AI in general — "AI literacy plan", "who needs which AI training", "EU AI Act Article 4 training", "rollout and change plan for our assistant", "adoption KPIs", "how many training hours". Produces a role-based curriculum (curriculum.csv), training load per wave and business unit (training-load.csv), an adoption plan (adoption-plan.md - Summary, Who needs what, Curriculum, Rollout, Adoption KPIs, Art. 4 note, Method) and adoption.json, from a population CSV (role, headcount, exposure, proficiency) and a module catalog (default curriculum shipped, labelled as the skill's own design). Overseers always get the human-oversight module; KPI targets are never defaulted. Not for an AI strategy or CoE operating model (use ai-strategy-coe), the release rollout of the system itself (use ai-release-plan) or legal advice on Article 4 scope.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: strategy
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: population, type: csv, required: true, from: "role,headcount,exposure,proficiency,business_unit (layout: assets/population-template.csv; exposure none|user|operator|builder|overseer; proficiency 0-3)"}
      - {name: catalog, type: csv, required: false, from: "module_id,title,hours,audience,level,format[,mandatory_for] (default: assets/literacy-modules.csv, the skill's own curriculum design)"}
      - {name: waves, type: csv, required: false, from: "wave,business_unit,start_date (layout: assets/waves-template.csv); missing waves are TBD for the Change lead"}
      - {name: targets, type: csv, required: false, from: "adoption KPI targets key,value,source (layout: assets/adoption-targets.csv); missing targets are TBD for the Change lead"}
      - {name: strict, type: flag, required: false, flag: "--strict", from: "true to fail the run (exit 1) when an operator or overseer role has no module mapped"}
    run:
      - {step: plan, kind: script, cmd: "python3 -I scripts/adoption_plan.py --population {population} [--catalog {catalog}] [--waves {waves}] [--targets {targets}] {strict} --out-dir {out}"}
    outputs:
      - {path: "{out}/curriculum.csv", checks: [exists, csv:[role,module_id,title,hours,reason], csv_rows:module_id!empty, "csv_rows:hours~^\\d+(\\.\\d+)?$", cmd:"python3 -I scripts/adoption_plan.py --verify {path}"]}
      - {path: "{out}/training-load.csv", checks: [exists, csv:[wave,business_unit,people,hours], csv_rows:wave!empty, "csv_rows:hours~^\\d+(\\.\\d+)?$"]}
      - {path: "{out}/adoption-plan.md", checks: [exists, sections:["Summary","Who needs what","Curriculum","Rollout","Adoption KPIs","Art. 4 note","Method"], no_unowned_tbd, contains:"does not require providers or deployers to guarantee"]}
      - {path: "{out}/adoption.json", checks: [exists, json, contains:"\"training_hours\"", cmd:"python3 -I scripts/adoption_plan.py --verify {path}"]}
---

# AI Adoption and Literacy Plan

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-adoption-and-literacy --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-adoption-and-literacy`). Report the `run.json` results; do not hand-write the deliverables the script produces (`curriculum.csv`, `training-load.csv`, `adoption-plan.md`, `adoption.json`). `--verify` recomputes every hour and seat total from `adoption.json`.

## When to use
- ADLC strategy stage: before an AI system (or AI tools in general) reaches staff, to plan who learns what, when, and how adoption is measured.
- "Which roles need which AI training, and how many hours is that per wave?"
- Evidence of EU AI Act Article 4 literacy measures (a record of measures, not a certificate).
- NOT for: the AI strategy or CoE operating model (`ai-strategy-coe`), the staged release of the system itself (`ai-release-plan`), legal determinations of provider/deployer status or high-risk scope (route to counsel).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `population` — role, headcount, exposure, proficiency, business_unit | yes | HR / Change lead (copy `assets/population-template.csv`) | run stops (exit 2), asks once |
| `catalog` — module_id, title, hours, audience, level, format, mandatory_for | no | L&D lead | default `assets/literacy-modules.csv` (the skill's own design, labelled so in the plan) |
| `waves` — wave, business_unit, start_date | no | Change lead (copy `assets/waves-template.csv`) | wave and start date are `[TO BE BASELINED — owner: Change lead]` |
| `targets` — key,value,source | no | Change lead / product owner (copy `assets/adoption-targets.csv`) | each KPI target is `[TO BE BASELINED — owner: Change lead]` |
| `strict` — true/false | no | Change lead | false: gaps reported, exit 0 |

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Fill the population: one row per role and business unit; set exposure and proficiency per `references/method.md`.
3. Review the default catalog with the L&D lead or supply your own; keep a `mandatory_for` overseer module.
4. Run the agent. A role needs a module when the module audience includes its exposure and the module level exceeds its proficiency; overseer-mandatory modules are always required.
5. Read the gaps: operator/overseer roles with no module and business units without a wave.
6. With `strict=true`, any operator/overseer role without a module fails the run (exit 1) — use it before go-live.
7. Run the self-check.

## Output
- `curriculum.csv` — `business_unit, role, module_id, title, hours, reason`.
- `training-load.csv` — `wave, business_unit, start_date, people, learners, hours`.
- `adoption-plan.md` — **Summary**, **Who needs what**, **Curriculum** (seats, seat-hours), **Rollout**, **Adoption KPIs**, **Art. 4 note**, **Method**.
- `adoption.json` — roles, modules, seats, totals, load, KPIs, gaps, gate.

## Self-check
- [ ] Every overseer has the human-oversight module; every operator/overseer has at least one module
- [ ] Hours and seats pass `--verify`
- [ ] KPI targets came from `targets` or are TBD for the Change lead; none invented
- [ ] The plan says when the default catalog (skill design) was used
- [ ] Art. 4 note uses the amended wording and says it is not a legal determination

## References
- `references/method.md` — exposure levels, proficiency scale, rules, gate, limits
- `references/sources.md` — EU AI Act Art. 4 (as amended by Regulation (EU) 2026/1744), Art. 3(56), Art. 26(2), Art. 113, with URLs and date checked
- `assets/literacy-modules.csv` — default curriculum (skill design)
- `assets/population-template.csv`, `assets/waves-template.csv`, `assets/adoption-targets.csv` — input layouts
- `scripts/adoption_plan.py` — planner and `--verify` (argparse; stdlib)
