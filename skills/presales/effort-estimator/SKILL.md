---
name: effort-estimator
description: Use when the user asks to size, estimate, or price a services engagement — "give me the price for <client>", "give me P50/P80/P90, staffing and price", "run the estimate on this WBS and rate card", "re-estimate and show what changed", or sizing a platform migration (e.g. "size the MuleSoft-to-Apigee migration") from interface counts by complexity band an assessment already produced. Builds a WBS with 3-point estimates, runs PERT + Monte Carlo (scripts/estimate.py) for P50/P80/P90 effort with contingency, a staffing table by role and phase with onshore/offshore mix, and a cost and margin roll-up against a rate card the user supplies (never invented rates or "industry-standard" unit efforts), plus an estimate memo. Do not use for scoring the interface inventory or wave plan (integration-migration-assessor), business-case benefits (value-case-builder) or the proposal narrative (proposal-writer).
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: wbs, type: csv, required: true, from: "user WBS file (layout: assets/wbs-template.csv)"}
      - {name: rates, type: csv, required: false, from: "user rate card (layout: assets/rate-card.example.csv); without it: effort only, no price"}
      - {name: client, type: string, required: true, from: "client name for the memo"}
      - {name: iterations, type: string, required: false, default: "20000"}
      - {name: currency, type: string, required: false, from: "reporting currency (ISO code) when the rate card mixes currencies"}
      - {name: fx, type: string, required: false, from: "sourced FX rates into the reporting currency, comma list CUR=rate (1 CUR = rate reporting currency), e.g. INR=0.012; needed with currency for a mixed-currency card"}
      - {name: previous, type: json, required: false, from: "estimate.json from the earlier run; adds the change vs the previous estimate (totals, phases, price)"}
      - {name: draft_only, type: flag, required: false, flag: "--draft-only", from: "true to skip the model step: estimate-memo.md is written from this run's figures, labelled as a draft"}
    run:
      - {step: model-json, kind: script, cmd: "python3 -I scripts/estimate.py {wbs} [--rates {rates}] --iterations {iterations} [--currency {currency}] [--fx {fx}] --seed 7 --json", stdout: "{out}/estimate.json"}
      - {step: model-report, kind: script, cmd: "python3 -I scripts/estimate.py {wbs} [--rates {rates}] --iterations {iterations} [--currency {currency}] [--fx {fx}] --seed 7 --out {out}/estimate.md [--previous {previous}] --memo {out}/estimate-memo.md --client {client} {draft_only}"}
      - {step: memo, kind: llm, template: assets/estimate-summary-template.md, context: ["{out}/estimate.md", "{out}/estimate.json", "references/estimation-method.md"], out: "{out}/estimate-memo.md", skip_if_present: [draft_only]}
    outputs:
      - {path: "{out}/estimate.json", checks: [exists, json]}
      - {path: "{out}/estimate.md", checks: [exists, sections:["Bottom line","Basis mix","By phase","Staffing"]]}
      - {path: "{out}/estimate-memo.md", checks: [exists, sections:["Bottom line","Basis of estimate","Assumptions","Risks"], no_unowned_tbd, numbers_trace_to:"{out}/estimate.md"]}
    modes:
      new: {case: agent-mode-new, bring: "a WBS filled in from the template and a rate card"}
      existing: {case: agent-mode-existing, bring: "your revised WBS plus the earlier estimate's results"}
---

# effort-estimator

## In a conversation: build the estimate now
The reply **is the estimate**, about 1,000 tokens: compact tables (WBS ≤ 12 rows), one line per point, no preamble — all seven parts must fit, so never spend the reply on one part. Never claim a Monte Carlo figure you did not compute: P50/P80/P90 come from the `estimate.py` run (quote them exactly when its output is in the conversation, else `[from estimate.py run — owner: Estimation lead]`); never write only a command.
- **The request carries scope counts** (e.g. "118 interfaces: 60 simple, 40 medium, 18 complex"), even when it says the actuals, WBS or rate card are attached but their contents are not in the conversation: write the estimate **in this reply**, in this order. Never reply with only a request for files.
  1. **WBS** in the `assets/wbs-template.csv` columns (`task_id, phase, work_package, task, role, driver_group, count, unit_o, unit_m, unit_p, …, basis, predecessors, notes`): parametric rows per band (count × unit effort, basis `PAR`, citing the prior actuals as the unit source), plus explicit PM, QA, environments, cutover, hypercare and KT packages. Unit efforts not in the conversation are `[TO BE BASELINED — owner: ___]` naming the attached actuals as source.
  2. **Model**: the exact command — `python3 -I scripts/estimate.py wbs.csv --rates rate-card.csv --iterations 20000 --out estimate.md` — and a results table P50 / P80 / P90 effort and cost with **contingency = P80 − P50** as its own column; figures not yet computed read `[TO BE BASELINED — owner: Estimation lead, from the estimate.py run]`.
  3. **Confidence quoted** per `references/estimation-method.md` §4, and why: fixed price, inventory known → P80; fixed price, inventory unconfirmed → P90 or assessment first; T&M → P50 with P80 as NTE.
  4. **Staffing table** by role and phase with onshore/offshore split, allocations between 20% and 100%, leverage ratio.
  5. **Price and margin**: price only from the supplied rate card (effort × bill rate), margin at P50 and at P80; rates not visible are `[TO BE BASELINED — owner: ___]`, never typical rates.
  6. **Assumptions**: every count and unit effort as a row with its source.
  7. **Memo** in the `assets/estimate-summary-template.md` sections: Bottom line, Basis of estimate (basis mix ANA/PAR/JUD %), Assumptions, Exclusions, Risks to the estimate and de-risking, Sensitivity, Staffing, Price-to-win.
- **WBS given (or said to be attached), no rate card** ("here is the WBS, give me the price"): ask once for the rate card with its columns (`role, grade, location, cost_rate, bill_rate, currency, valid_until`), and in the same reply produce the **effort-only output**: `| | P50 | P80 | P90 | Contingency (P80 − P50) |` effort row (from the WBS run, or `[from estimate.py run]` when the WBS content is not visible), the staffing table by role and phase, and a price row that reads exactly **`Price: [TO BE BASELINED — owner: ___] — no rate card supplied; no rates assumed`**.
- **No WBS and no scope** ("give me the price for Acme"): ask once for the WBS (`assets/wbs-template.csv`) — `estimate.py` cannot run without it — and the rate card; invent no tasks.
- **WBS and rate card attached**: line 1 the command — `python3 -I scripts/estimate.py wbs.csv --rates rates.csv --iterations 20000 --seed 7 --out estimate.md --memo estimate-memo.md --client <client> [--previous estimate-previous.json] [--draft-only]` (+ `--json` → `estimate.json`) — then P50/P80/P90 with contingency = P80 − P50, staffing, price and margin, and the memo in the template sections (Bottom line, Basis of estimate, Assumptions, Risks). `draft_only` / "no LLM": the memo is written from the run's figures, **labelled as a draft**, every figure tracing to `estimate.md`.
- **Re-estimate with a previous `estimate.json`**: a change table `| Item | Previous | Now | Change |` for P80 effort, each phase (a phase absent before is "new"), and price at P80 — previous values copied exactly from the file, current values from this run — and the memo repeats that table.
- **No scope or WBS at all**: ask once, in one list, for the scope counts, phases, commercial model and rate card; say no counts, unit efforts or rates will be invented.
- **Asked to use an "industry-standard" unit effort or quote fixed price at P50**: decline in one line (there is no sourced industry standard; a P50 fixed price carries no contingency, so it loses money half the time). Do not supply an industry figure. Use the user's own figure (e.g. 3 days per interface) only if they confirm it as their assumption, labelled `JUD`, with the anchor source `[TO BE BASELINED — owner: ___]`. Flag that `JUD` > 30% of effort makes the estimate low-confidence and recommend an assessment phase or per-unit pricing with a count band. Do not stop at asking — show, in this reply: `| Unit effort | 3 days/interface — user's figure, basis JUD | anchor source [TO BE BASELINED — owner: ___] |`; `Basis mix: JUD 100% > 30% → low confidence → recommend an assessment phase, or per-unit pricing with a count band`; `| | P50 | P80 | Contingency (P80 − P50) |` side by side; and the recommendation P80/P90 fixed or T&M with a P80 NTE.

## Starting points
- **New** — your WBS (and rate card) is modelled: P10–P90 effort, phases, variance contributors, staffing, cost and price; the model step writes the memo, or with `draft_only` the memo is written from the run's figures, every number traceable.
- **Existing** — add `previous` (the earlier run's `estimate.json`): the re-estimate shows what changed — totals, each phase and price at P80, previous → now — in the report and the memo.

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
3. **Run the model**: `python3 -I scripts/estimate.py wbs.csv --rates rate-card.csv --iterations 20000 --out estimate.md`. Outputs P50/P80/P90 effort and cost, per-phase distribution, staffing table, and a sensitivity list (tasks contributing most variance). Without `--rates`, the script outputs effort only. Rates match on role AND location (add a WBS `location` column when a role is priced onshore and offshore); a mixed-currency card needs `--currency` and sourced `--fx CUR=rate`, otherwise the script stops. The script does not compute duration; the memo derives it from the critical path and staffing plan or marks it `[TO BE BASELINED — owner: Estimation lead]`.
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

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/effort-estimator --input <name>=<value> … --out <dir>` (see `--explain presales/effort-estimator`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

## References
- `references/estimation-method.md` — WBS rules, 3-point calibration, PERT/Monte Carlo, confidence selection, sensitivity
- `references/staffing-and-rates.md` — pyramid design, onshore/offshore, leverage, margin sanity, rate-card contract
- `assets/wbs-template.csv` — WBS input layout
- `assets/rate-card.example.csv` — rate-card layout with EXAMPLE placeholder rows (replace with real rates; never ship)
- `assets/estimate-summary-template.md` — memo template
- `scripts/estimate.py` — PERT + Monte Carlo, staffing table, cost roll-up
