---
name: value-case-builder
description: Use when the user asks to build, structure, or review a business case, value case, ROI model, benefits case, or cost-benefit analysis for a client initiative or internal investment. Produces a benefits tree (driver → lever → metric → value), a cost and savings model layout (CSV spec plus markdown), payback and multi-year net, sensitivity on the top drivers, and a benefits-realization plan with owners; every number is sourced to a client document or statement or marked [TO BE BASELINED — owner: ___]. Do not use for platform-only TCO (integration-migration-assessor feeds this) or for effort (effort-estimator).
license: MIT
metadata:
  domain: presales
  adlc_stage: use-case
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: benefits, type: csv, required: true, from: "benefits.csv: benefit_id, name, driver, unit_value, units_per_year, ramp_pct_y1..y3, source (layout: evals/fixtures/benefits.csv)"}
      - {name: costs, type: csv, required: true, from: "costs.csv: cost_id, name, one_time, run_rate_per_year, start_year, source (layout: evals/fixtures/costs.csv)"}
      - {name: discount_rate, type: string, required: false, from: "client finance's rate as a fraction, e.g. 0.08; without it NPV is [TO BE BASELINED]"}
      - {name: p80_cost_uplift, type: string, required: false, from: "P80/P50 uplift on cost as a fraction, from the estimate memo; without it P80 cost is [TO BE BASELINED]"}
      - {name: years, type: string, required: false, default: "5"}
      - {name: client, type: string, required: false, default: "<Client>"}
      - {name: previous, type: json, required: false, from: "value-model.json of the earlier value case; adds what changed in the totals and in each benefit"}
    run:
      - {step: model, kind: script, cmd: "python3 -I scripts/value_model.py {benefits} {costs} --years {years} [--discount-rate {discount_rate}] [--p80-cost-uplift {p80_cost_uplift}] [--previous {previous}] --client {client} --json {out}/value-model.json --out {out}/value-case.md"}
    outputs:
      - {path: "{out}/value-model.json", checks: [exists, json]}
      - {path: "{out}/value-case.md", checks: [exists, sections:["Bottom line","Cash flows","Sensitivity","Sources"], numbers_trace_to:"{out}/value-model.json"]}
    modes:
      new: {case: agent-happy-path, bring: "benefits and costs with their sources"}
      existing: {case: agent-mode-existing, bring: "updated benefits and costs plus the last value case"}
---

# value-case-builder

## In a conversation: build the case now
- **The request carries baselines** (volumes, costs, rates from client sources): write the value case **in this reply**. A benefits tree tracing each lever to the client's statements and cost drivers; baselines cited with confidence (H/M/L); unbaselined benefits kept out of the headline and listed; targets as low/base/high with mechanisms and ramps tied to delivery milestones; costs including delivery (at the estimate's P80), run, dual-run and decommission timing; NPV only at a discount rate the client's finance supplied, on their fiscal year; sensitivity on the top three assumptions with break-even values; a benefits-realization plan with client owners (unowned benefits flagged); a double-counting check.
- **The request says files are attached but their contents are not in the conversation**: still build the whole case now from the facts the request states (who said what, which sources exist, the discount rate, the fiscal year). Lay out every section in full — benefits tree, baselines table, targets, costs, NPV, sensitivity, realization plan, double-counting check — with each value the request does not give shown as `[TO BE BASELINED — owner: ___]` naming the attached source it will come from. Never reply with only a request for the files.
- **No client baselines**: ask once for scope, outcomes, at least one baseline fact and the audience. If none are available, say on line 1 that this is not a business case yet, give a hypothesis map (benefits tree with every baseline `[TO BE BASELINED — owner: ___]`) and the specific data requests with their likely holders.
- **Asked to use an industry benchmark or put a big multiple on page one**: decline in one line (a CFO-grade case is built from the client's baselines and mechanisms; an unsourced multiple will not survive finance review). Show the headline as `[TO BE BASELINED — owner: ___]` — never print the requested multiple or percentage anywhere, not even beside that marker — list the unbaselined benefits, and offer the path to a defensible number: data requests with owners and a short baselining phase. A benchmark the user supplies with a source is recorded at confidence L and kept out of the headline.

## Starting points
- **New** — sourced benefits and costs become a CFO-grade value case: yearly cash flows, NPV, payback, P80 cost and sensitivity, with unbaselined rows kept out of the headline.
- **Existing** — add `previous` (the earlier case's `value-model.json`): the refresh shows how benefits, costs, net, NPV, P80 cost and payback moved, and which benefits were added, removed, re-estimated or newly baselined.

## When to use
- "Build the business case for <initiative>."
- "What is the ROI on this program, and how confident are we?"
- "Review the client's draft business case before the steering committee."
- NOT for: platform TCO alone (`integration-migration-assessor`), effort and price (`effort-estimator`), the proposal narrative (`proposal-writer`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Initiative scope and outcomes (objectives, success measures) | yes | discovery synthesis / proposal |
| Baseline facts: current cost, volumes, cycle times, headcount on the process, error/incident rates, revenue levers | yes (any subset; rest is TBD) | client documents / statements |
| Cost of the initiative: one-time (from `effort-estimator`) and run (from TCO or client) | yes or `[TO BE BASELINED]` | estimate memo / TCO |
| Finance conventions: currency, horizon (3/5 yr), discount rate, capex/opex treatment, fiscal year | no — defaults stated as assumptions | client finance / user |
| Audience: CFO-grade vs sponsor-level | yes | user |

If scope and at least one baseline fact are missing, ask once. A value case with no client baseline is a hypothesis map, and the output says so on line 1.

## Procedure
Read `../../shared/quality-bar.md` and `../../shared/writing-style.md` first.

1. **Build the benefits tree** per `references/value-method.md` §1: strategic driver → value lever → operational metric → financial value. Each leaf must trace to an outcome the client stated. Classify each benefit: hard (cash, cost avoided with a named budget line), soft-quantifiable (productivity hours with a conversion rule), strategic (unquantified; listed, not summed).
2. **Baseline every metric**: value, source (document/page or client role and date), confidence (H/M/L). No source → `[TO BE BASELINED — owner: ___]` and the metric is excluded from the headline number until baselined. Do not borrow benchmarks from memory; if the user supplies an external benchmark, cite it and rate confidence L.
3. **Set improvement targets** as ranges (low / base / high) with the mechanism that produces them (automation of step X removes Y hours; decommission removes licence line Z). A target without a mechanism is not admissible. Ramp realization over time per §3 (benefits rarely start at 100% on go-live).
4. **Model costs**: one-time (delivery at P80 from the estimate memo, licences, change management, decommission), run (new platform, support, subscriptions), and the cost of delay for the status quo if evidenced. Cite sources; mark unknowns.
5. **Decision point — headline metric.** With the finance conventions in hand choose: simple payback and multi-year net (sponsor-level) or NPV/IRR (CFO-grade). State the discount rate as an assumption with owner. Never present NPV if the discount rate is not from the client's finance team; use undiscounted net and say so.
6. **Compute and lay out** on `assets/value-model-spec.md` (CSV layout) and `assets/value-case-template.md` (markdown). Any output depending on a `[TO BE BASELINED]` input is itself marked, not computed from a placeholder.
7. **Sensitivity**: identify the three assumptions with the largest effect on 3-year net; show ±20% (or the realistic range) and the break-even value of each. If the case flips sign within the realistic range, say so on line 1.
8. **Benefits-realization plan**: each benefit with a KPI, baseline, target, measurement method, owner (client), review cadence, and the realization start date tied to a delivery milestone. Benefits without a client owner are listed as unowned risks.
9. **Risks to the case**: adoption, dependency on other programs, data quality, timing of decommission, double counting (check overlap between levers).
10. Review mode: apply the rubric in `references/value-case-review-rubric.md`, redline per convention, deliver clean version.
11. Run the self-check.

## Output
| Artifact | File |
|---|---|
| Value model (CSV layout) | `value-model-<client>-<initiative>.csv` per `assets/value-model-spec.md` |
| Value case document | `value-case-<client>-<initiative>-<yyyy-mm-dd>.md` per `assets/value-case-template.md` |

Sections: Bottom line (headline metric with confidence and what is unbaselined) · Benefits tree · Baselines and sources · Targets and mechanisms · Costs · Model (yearly table, payback, net) · Sensitivity · Benefits-realization plan · Risks · Assumptions register · Decision asked

## Self-check
- [ ] Every benefit traces to a client-stated outcome and has a mechanism
- [ ] Every baseline has source and confidence or is `[TO BE BASELINED — owner: ___]`
- [ ] Headline number excludes unbaselined benefits; the exclusion is stated
- [ ] Strategic benefits listed, not summed
- [ ] Costs include run and decommission timing; delivery cost cites the estimate memo
- [ ] Sensitivity on top three assumptions with break-even values
- [ ] Every benefit has a client owner or is flagged unowned
- [ ] No double counting across levers; no benchmarks from memory

## References
- `references/value-method.md` — benefits tree, classification, baselining, targets and ramps, finance conventions, double-counting checks
- `references/value-case-review-rubric.md` — review criteria for an existing business case
- `assets/value-model-spec.md` — CSV layout specification
- `assets/value-case-template.md` — markdown document template

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/value-case-builder --input <name>=<value> … --out <dir>` (see `--explain presales/value-case-builder`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

