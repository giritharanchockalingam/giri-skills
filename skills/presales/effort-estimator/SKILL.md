---
name: effort-estimator
description: Use when the user asks to size, estimate, or price a services engagement, build a WBS, produce P50/P80/P90 effort and duration, design a staffing pyramid or onshore/offshore mix, or sanity-check margin. Produces a WBS with 3-point estimates, a Monte Carlo (PERT) distribution with confidence levels, a staffing table by role and phase, and a cost roll-up against a rate card the user supplies (never invented rates). Includes a script that runs PERT + Monte Carlo over a WBS CSV. Do not use for business-case benefits (value-case-builder) or for the proposal narrative (proposal-writer).
license: MIT
metadata:
  domain: presales
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: wbs, type: csv, required: true, from: "user WBS file (layout: assets/wbs-template.csv)"}
      - {name: rates, type: csv, required: false, from: "user rate card (layout: assets/rate-card.example.csv); without it: effort only, no price"}
      - {name: client, type: string, required: true, from: "client name for the memo"}
      - {name: iterations, type: string, required: false, default: "20000"}
    run:
      - {step: model-json, kind: script, cmd: "python3 -I scripts/estimate.py {wbs} [--rates {rates}] --iterations {iterations} --seed 7 --json", stdout: "{out}/estimate.json"}
      - {step: model-report, kind: script, cmd: "python3 -I scripts/estimate.py {wbs} [--rates {rates}] --iterations {iterations} --seed 7 --out {out}/estimate.md"}
      - {step: memo, kind: llm, template: assets/estimate-summary-template.md, context: ["{out}/estimate.md", "{out}/estimate.json", "references/estimation-method.md"], out: "{out}/estimate-memo.md"}
    outputs:
      - {path: "{out}/estimate.json", checks: [exists, json]}
      - {path: "{out}/estimate.md", checks: [exists, sections:["Bottom line","Basis mix","By phase","Staffing"]]}
      - {path: "{out}/estimate-memo.md", checks: [exists, sections:["Bottom line","Basis of estimate","Assumptions","Risks"], no_unowned_tbd, numbers_trace_to:"{out}/estimate.md"]}
---

# effort-estimator

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/effort-estimator --input <name>=<value> … --out <dir>` (see `--explain presales/effort-estimator`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

## When to use
- "Size the <initiative> engagement."
- "Give me P50/P80 for this WBS."
- "What team do we need and what is the onshore/offshore split?"
- "Does this price hold margin?"
- NOT for: benefits and ROI (`value-case-builder`), interface-level complexity scoring (`integration-migration-assessor` feeds this skill), narrative (`proposal-writer`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Scope definition: deliverables, counts (interfaces, components, sites, users), phases | yes | discovery synthesis / architecture doc / assessor output |
| Rate card CSV (role, location, cost rate, bill rate, currency) | yes for cost/price; else effort-only | user file (`assets/rate-card.example.csv` shows the layout) |
| Constraints: deadline, team-size cap, onshore/offshore policy, client-side availability | no | user |
| Target margin or price-to-win (if known) | no | user |
| Prior actuals for similar work (if any) | no | user file |

If scope counts are missing, ask once; otherwise estimate per unit and mark counts `[TO BE BASELINED — owner: ___]` so the total scales. If the rate card is missing, produce effort and staffing only; never invent rates.

## Procedure
Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md` first.

1. **Decompose to a WBS** per `references/estimation-method.md` §1: phases → work packages → tasks sized 2–15 person-days. Each task carries a driver (count × unit effort) or a fixed effort, a role mix, and a dependency. Keep management, QA, environments, cutover, hypercare, and knowledge transfer as explicit packages; they are the most frequently omitted.
2. **Assign 3-point estimates** (optimistic, most likely, pessimistic) per task using the calibration rules in §2. Pessimistic is the "things go wrong but not catastrophic" case, typically 1.5–3× most-likely. Record the basis for each: analogy (prior actual), parametric (count × unit), or expert judgment. Expert judgment on >30% of effort is a flag in the output.
3. **Run the model**: `python3 -I scripts/estimate.py wbs.csv --rates rate-card.csv --iterations 20000 --out estimate.md`. Outputs P50/P80/P90 effort and cost, per-phase distribution, staffing table, and a sensitivity list (tasks contributing most variance). Without `--rates`, the script outputs effort only.
4. **Decision point — confidence level to quote.** Per §4: fixed-price → P80 minimum, P90 for migrations with unknown inventories; T&M → P50 as the estimate with P80 as the not-to-exceed; assessments → fixed at P80 with a short duration. State which was used and why.
5. **Build the staffing pyramid** per `references/staffing-and-rates.md`: roles, grades, allocation by phase, onshore/offshore split against policy and client constraints, ramp-up and ramp-down, leverage ratio. Check span of control and that no role is allocated above 100% or below a useful minimum (20%).
6. **Cost and margin**: cost = effort × cost rate; price = effort × bill rate or target-margin markup; contingency = (P80 − P50) shown explicitly, not buried in rates. Compare with price-to-win if given; if the gap exceeds 15%, list scope or mix levers rather than cutting the estimate.
7. **Write the estimate memo** on `assets/estimate-summary-template.md`: bottom line (P80 effort, duration, team, price or "price pending rate card"), basis of estimate, assumptions (every count and rate), exclusions, risks to the estimate, sensitivity.
8. Run the self-check.

## Output
| Artifact | File |
|---|---|
| WBS with 3-point estimates | `wbs-<client>-<initiative>.csv` (layout: `assets/wbs-template.csv`) |
| Model output | `estimate-<client>-<initiative>.md` (from script) |
| Estimate memo | `estimate-memo-<client>-<initiative>.md` (template: `assets/estimate-summary-template.md`) |

## Self-check
- [ ] WBS includes PM, QA, environments, cutover, hypercare, KT packages
- [ ] Every task has basis (analogy / parametric / judgment); judgment share reported
- [ ] Confidence level chosen and justified against the commercial model
- [ ] Contingency shown explicitly as P80 − P50
- [ ] Rates only from the supplied rate card; no rates if none supplied
- [ ] Every count is an assumption row with `[TO BE BASELINED — owner: ___]` where unconfirmed
- [ ] Staffing allocations between 20% and 100%; leverage ratio stated
- [ ] Totals reconcile across WBS, model output, and memo

## References
- `references/estimation-method.md` — WBS rules, 3-point calibration, PERT/Monte Carlo, confidence selection, sensitivity
- `references/staffing-and-rates.md` — pyramid design, onshore/offshore, leverage, margin sanity, rate-card contract
- `assets/wbs-template.csv` — WBS input layout
- `assets/rate-card.example.csv` — rate-card layout with EXAMPLE placeholder rows (replace with real rates; never ship)
- `assets/estimate-summary-template.md` — memo template
- `scripts/estimate.py` — PERT + Monte Carlo, staffing table, cost roll-up
