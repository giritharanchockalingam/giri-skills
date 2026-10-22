---
name: integration-migration-assessor
description: Use when the user asks to assess, score, plan, or build the case for migrating an integration or middleware estate between platforms (iPaaS to API gateway, ESB to event backbone, ETL tool to cloud data integration, any platform-to-platform move). Produces an interface inventory scored on complexity factors, a wave plan with entry/exit criteria, a TCO/ROI model layout with every figure sourced or marked [TO BE BASELINED — owner: ___], and a migration-factory approach. Includes a script that scores an API/interface inventory CSV and assigns waves. Do not use for the architecture document itself (solution-architecture-doc), effort math (effort-estimator), or benefits narrative (value-case-builder); this skill feeds all three. Not for sizing or pricing a migration whose interface counts by band are already assessed — P50/P80/P90, staffing, price (effort-estimator).
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: inventory, type: csv, required: true, from: "interface inventory (columns: assets/inventory-columns.md)"}
      - {name: rates, type: csv, required: true, from: "rate inputs key,value,unit,source (keys in scripts/tco.py --help); no prices are ever assumed"}
      - {name: client, type: string, required: true}
      - {name: waves, type: string, required: false, default: "3"}
      - {name: draft_only, type: flag, required: false, flag: "--draft-only", from: "true to skip the model step: readout.md is assembled from the scoring and TCO summaries, labelled as a draft"}
    run:
      - {step: score, kind: script, cmd: "python3 -I scripts/score_inventory.py {inventory} --out {out}/scored.csv --waves {waves} --summary", stdout: "{out}/scoring-summary.md"}
      - {step: tco, kind: script, cmd: "python3 -I scripts/tco.py {out}/scored.csv --rates {rates} --out {out}/tco.csv --summary {out}/tco-summary.md --json {out}/tco.json"}
      - {step: readout, kind: llm, template: assets/assessment-readout-template.md, context: ["{out}/scoring-summary.md", "{out}/tco-summary.md", "references/migration-factory-method.md"], out: "{out}/readout.md", skip_if_present: [draft_only]}
      - {step: readout-draft, kind: script, cmd: "python3 -I scripts/readout_draft.py --scoring {out}/scoring-summary.md --tco {out}/tco-summary.md --client {client} --out {out}/readout.md", skip_if_missing: [draft_only]}
    outputs:
      - {path: "{out}/scored.csv", checks: [exists, csv:[interface_id,weighted_score,band,wave,retire_candidate]]}
      - {path: "{out}/tco.csv", checks: [exists, csv:[scenario,category,line,year,amount,source]]}
      - {path: "{out}/tco.json", checks: [exists, json]}
      - {path: "{out}/readout.md", checks: [exists, sections:["Bottom line","Scoring results","Wave plan","TCO","Risks","Next steps"], no_unowned_tbd, numbers_trace_to:["{out}/scoring-summary.md","{out}/tco-summary.md"]]}
    modes:
      existing: {case: agent-mode-existing, bring: "the interface inventory of the current estate and rate inputs"}
---

# integration-migration-assessor

## In a conversation: assess now
- **The request carries the inventory** (or its contents): produce the readout **in this reply**. Report the share of unknown factors and whether the assessment is provisional; list retirement candidates with owners to confirm before effort is discussed; a band distribution table with outliers explained; a wave plan (wave 0 foundation, a representative wave 1, balanced middle waves, dependencies enforced, cutovers outside the client's freeze windows, entry/exit criteria); TCO lines that cite the client's contract for licence cost, with migration cost `[TO BE BASELINED — owner: ___]` until the effort estimate exists; handoffs to effort-estimator and solution-architecture-doc.
- **No inventory, only a count**: ask once for the inventory and offer the collection template (`assets/inventory-columns.md`) and the minimum viable column set for a provisional assessment. Never synthesize an inventory or a band distribution from a count.
- **Asked to use list prices, treat blanks as simple, or give a ballpark savings figure**: say in one line why not (blank factors scored simple are the main cause of overrun; vendor list prices from memory are not the client's contract). Score blanks as unknown (mid-band, flagged); show licence cost and savings as `[TO BE BASELINED — owner: ___]` naming the client contract as the source; state the TCO direction qualitatively at most; give next steps with owners.

## Starting points
- **Existing** — the inventory of your current estate is scored, banded and planned into waves, the TCO is built only from the rate inputs you supply, and the readout is written by the model step or, with `draft_only`, assembled from the two summaries with every figure copied verbatim.
- Only for existing: an assessment always scores an integration estate that already runs; there is nothing to assess from scratch.

## When to use
- "Assess <client>'s MuleSoft/Boomi/ESB/Informatica estate for migration to <target>."
- "Score this interface inventory and give me waves."
- "Build the TCO comparison for staying vs migrating."
- NOT for: drawing the target architecture (`solution-architecture-doc`), P50/P80 effort (`effort-estimator`), full business case with non-platform benefits (`value-case-builder`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Interface inventory CSV (one row per interface/API/flow; columns per `assets/inventory-columns.md`) | yes | client export / discovery / platform admin console export |
| Source and target platforms (or "target to be selected") | yes | user |
| Current platform cost facts: licence, infrastructure, support/run team, contract end | no — TCO is `[TO BE BASELINED]` without them | client / user |
| Constraints: freeze windows, contract end dates, dependent programs (ERP upgrade), compliance | no | discovery |
| Prior migration actuals (unit effort per band) if any | no | user |

If the inventory is missing, ask once; offer `assets/inventory-columns.md` as the collection template. Never synthesize an inventory.

## Procedure
Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md` first.

1. **Validate the inventory**: run `python3 -I scripts/score_inventory.py inventory.csv --validate`. It reports missing columns, blank factor cells, and duplicates. Blank factor cells score as "unknown" (mid-band with a flag), never as "simple". Report the unknown share; above 25% the assessment is provisional and says so.
2. **Score complexity** with `python3 -I scripts/score_inventory.py inventory.csv --out scored.csv --waves 4`. Factors and weights per `references/complexity-scoring.md` (pattern, transformation logic, protocol/connector availability on target, endpoints, data volume, error handling and orchestration, security, test coverage, documentation, business criticality). Review the band distribution (Simple / Medium / Complex / Very complex) against what discovery said; investigate outliers.
3. **Decision point — migration approach per band.** Apply `references/migration-factory-method.md` §2: Simple → automated/tool-assisted conversion with templated tests; Medium → factory with pattern templates; Complex → design-led with refactor; Very complex → candidates for redesign, retirement, or re-platform outside the factory. Retirement candidates (unused, duplicate, superseded) are identified first; they are the cheapest migration.
4. **Assign waves** (script output, then adjust): wave 0 foundation; wave 1 representative simples; middle waves balance complexity and resolve dependencies; final wave long-tail and decommission. Respect freeze windows and dependent programs from constraints. Each wave gets entry/exit criteria and a rollback approach from §4 of the method.
5. **Build the TCO/ROI layout** on `assets/tco-model-spec.md` (CSV layout spec) and `assets/tco-model.md` (markdown table layout): current run-rate (licence, infra, people, support, incidents) vs target run-rate, one-time migration cost (from `effort-estimator`, or `[TO BE BASELINED]`), timing of savings (only after decommission), 3–5-year view, payback, sensitivity on the two biggest drivers. Every figure sourced to a client document or marked. Licence savings are not realized until the source platform is decommissioned; model that date explicitly.
6. **Risk register for the migration**: dual-run cost, connector gaps on target, skills, endpoint changes during migration, data drift, cutover windows, vendor cooperation; each with likelihood, impact, mitigation, owner.
7. **Write the assessment readout** on `assets/assessment-readout-template.md`: bottom line (inventory size, band mix, approach, waves, TCO direction with confidence, decision asked), evidence, scoring results, wave plan, TCO layout, risks, next steps. Feed interface counts and bands to `effort-estimator` and the wave plan to `solution-architecture-doc`.
8. Run the self-check.

## Output
| Artifact | File |
|---|---|
| Scored inventory | `inventory-scored-<client>.csv` (script) |
| Wave plan | within readout; CSV wave column in scored inventory |
| TCO model layout | `tco-<client>.csv` per `assets/tco-model-spec.md` + markdown table in readout |
| Assessment readout | `migration-assessment-<client>-<yyyy-mm-dd>.md` |

## Self-check
- [ ] Inventory validated; unknown-factor share reported; provisional flag if >25%
- [ ] Band distribution reviewed against discovery; outliers explained
- [ ] Retirement candidates identified before scoring effort
- [ ] Waves have entry/exit criteria, rollback, and respect constraints
- [ ] TCO: every figure sourced or `[TO BE BASELINED — owner: ___]`; savings timed after decommission
- [ ] Sensitivity on the two largest drivers shown
- [ ] No vendor pricing quoted from memory; licence figures from client contracts or marked
- [ ] No other-client specifics; no author history

## References
- `references/complexity-scoring.md` — factors, weights, bands, unknown handling, calibration
- `references/migration-factory-method.md` — approach per band, factory operating model, wave rules, cutover and rollback, decommission
- `assets/inventory-columns.md` — inventory CSV column spec (collection template)
- `assets/tco-model-spec.md` — TCO/ROI CSV layout spec
- `assets/tco-model.md` — TCO markdown table layout
- `assets/assessment-readout-template.md` — readout template
- `scripts/score_inventory.py` — validate, score, band, assign waves

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/integration-migration-assessor --input <name>=<value> … --out <dir>` (see `--explain presales/integration-migration-assessor`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

