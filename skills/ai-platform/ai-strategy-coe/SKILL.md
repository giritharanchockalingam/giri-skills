---
name: ai-strategy-coe
description: Use when the user asks to design an enterprise AI strategy, stand up or assess an AI Center of Excellence (CoE), score an AI use-case portfolio, or build a 12-month AI roadmap. Produces a 5-level maturity assessment (data, platform, talent, governance, value), an operating-model recommendation (central / hub-and-spoke / federated), a scored use-case portfolio, a governance outline, and a quarter-by-quarter roadmap. Not for a single use case (use ai-use-case-canvas) or compliance-only reviews (use ai-governance-risk).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: strategy
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-happy-path, bring: "a rough list of AI ideas and a maturity self-assessment"}
      existing: {case: agent-mode-existing, bring: "re-scored use cases plus last review's ranked portfolio"}
    inputs:
      - {name: use_cases, type: csv, required: true, from: "use-case scoring CSV: id, use_case, business_owner, value_V, feasibility_F, data_readiness_D, risk_R (1-5), baseline_metric, evidence (layout: assets/use-case-scoring.csv + evidence column; fixture: evals/fixtures/use-cases.csv)"}
      - {name: scorecard, type: csv, required: true, from: "maturity scorecard CSV: dimension, score_1_to_5, evidence, gap_to_next_level, owner (layout: assets/maturity-scorecard.csv)"}
      - {name: org, type: string, required: false, default: "<Organization>"}
      - {name: previous_portfolio, type: csv, required: false, from: "portfolio.csv from the last portfolio review; adds rank and band movement, new and dropped use cases"}
      - {name: target_level, type: string, required: false, default: "3", from: "target maturity level 1-5; dimensions below it are gaps"}
      - {name: default_owner, type: string, required: false, default: "AI CoE lead", from: "who owns a gap the scorecard leaves without an owner"}
    run:
      - {step: portfolio, kind: script, cmd: "python3 -I scripts/score_portfolio.py {use_cases} --out-dir {out} --org {org} [--previous {previous_portfolio}]"}
      - {step: maturity, kind: script, cmd: "python3 -I scripts/maturity.py {scorecard} --out-dir {out} --org {org} --target {target_level} --default-owner {default_owner}"}
    outputs:
      - {path: "{out}/portfolio.csv", checks: [exists, csv:[rank,id,use_case,score,band], csv_rows:score!empty, csv_rows:band!empty]}
      - {path: "{out}/unscored.csv", checks: [exists, csv:[id,use_case,reason]]}
      - {path: "{out}/portfolio.md", checks: [exists, sections:["Ranked portfolio","Band summary","Quadrant summary","Unscored"]]}
      - {path: "{out}/maturity.md", checks: [exists, sections:["Level per dimension","Gaps"], no_unowned_tbd]}
      - {path: "{out}/roadmap.md", checks: [exists, sections:["Executive summary","Maturity","Gap closure items","Quarter plan"]]}
---

# AI Strategy & CoE Design

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-strategy-coe --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-strategy-coe`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`portfolio.csv`, `portfolio.md`, `maturity.md`, `roadmap.md`); fill the operating-model and governance sections of the roadmap by hand from the references.

## Starting points
- **New:** a first list of scored AI ideas and a maturity self-assessment give a ranked portfolio, maturity gaps and a quarter roadmap.
- **Existing:** add the `portfolio.csv` from your last review (`previous_portfolio`); the re-ranked portfolio shows each use case's rank and band movement, what is new and what dropped out or lost its scores.

## When to use
- "Build our AI strategy", "stand up an AI CoE", "where are we on AI maturity", "prioritize our AI backlog", "12-month AI roadmap".
- Executive audience: CIO, CDO, CTO, board.
- NOT for: qualifying one idea (`ai-use-case-canvas`), risk/compliance only (`ai-governance-risk`), agent design (`agent-architecture`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Organization context (industry, size, regulatory posture) | yes | user |
| Current-state evidence (data platforms, cloud, existing AI/ML, team) | yes | user / documents |
| Candidate use-case list (even rough) | no | user; skill elicits if missing |
| Executive sponsor and budget envelope | no | user; mark `[TO BE BASELINED — owner: ___]` if absent |
| Strategic priorities for the next 12 months | yes | user / annual plan |

If organization context or current-state evidence is missing, ask once. Do not infer maturity from industry averages.

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md`.
2. **Assess maturity.** Score each of the five dimensions 1–5 using `references/maturity-model.md`. Record evidence per score in `assets/maturity-scorecard.csv`. A score without evidence is `[TO BE BASELINED]`.
3. **Pick the operating model.** Apply the decision table in `references/operating-models.md`. State the chosen model, the two rejected ones, and why. Maturity level and organizational breadth drive this, not preference.
4. **Score the portfolio.** Score every candidate use case on value, feasibility, risk, data readiness (1–5 each) with `references/use-case-scoring.md`; fill `assets/use-case-scoring.csv`. Compute priority = value × feasibility × data readiness ÷ risk. Classify: Now / Next / Later / Stop.
5. **Define governance.** Minimum: intake gate, risk tiering, model inventory, review cadence. Point deeper controls to `ai-governance-risk`.
6. **Build the roadmap.** Use `assets/roadmap.md` with `references/roadmap-skeleton.md`. Q1 is foundations and 1–2 lighthouse use cases; never schedule scale before measurement exists.
7. **Write the executive summary** (≤5 bullets): maturity headline, model choice, top-3 use cases, investment envelope or `[TO BE BASELINED]`, first 90-day commitments.
8. Run the self-check.

## Output
- `ai-strategy-<org>.md`: exec summary, maturity table, operating model, portfolio table, governance, roadmap, risks, next steps (owner + date).
- `maturity-scorecard.csv` and `use-case-scoring.csv` filled.
- Saved to the working directory unless the user names a path.

## Self-check
- [ ] Every maturity score has an evidence line or a `[TO BE BASELINED — owner: ___]` marker
- [ ] Operating model choice cites the decision criteria it satisfied
- [ ] Portfolio table has every candidate scored on all four axes; no "high/med/low" without the numeric score
- [ ] Roadmap quarters each have an exit criterion and an owner
- [ ] No vendor named as a recommendation without a stated selection criterion
- [ ] No invented benchmark figures; industry comparisons carry a source or are omitted
- [ ] First line is the answer

## References
- `references/maturity-model.md` — 5-level model with criteria per dimension
- `references/operating-models.md` — central / hub-and-spoke / federated, when to choose
- `references/use-case-scoring.md` — rubric and formula
- `references/roadmap-skeleton.md` — 12-month quarter plan with exit criteria
- `scripts/score_portfolio.py` — scoring CSV → ranked `portfolio.csv` + `unscored.csv` + `portfolio.md`
- `scripts/maturity.py` — scorecard CSV → `maturity.md` + `roadmap.md` skeleton (one item per gap)
