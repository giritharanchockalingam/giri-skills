---
name: value-case-builder
description: Use when the user asks to build, structure, or review a business case, value case, ROI model, benefits case, or cost-benefit analysis for a client initiative or internal investment. Produces a benefits tree (driver → lever → metric → value), a cost and savings model layout (CSV spec plus markdown), payback and multi-year net, sensitivity on the top drivers, and a benefits-realization plan with owners; every number is sourced to a client document or statement or marked [TO BE BASELINED — owner: ___]. Do not use for platform-only TCO (integration-migration-assessor feeds this) or for effort (effort-estimator).
license: MIT
metadata:
  domain: presales
  version: 0.1.0
  author: giri-skills
---

# value-case-builder

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
Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md` first.

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
