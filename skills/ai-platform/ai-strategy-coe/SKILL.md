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

## In a conversation: write the strategy now
The reply **is the deliverable** (or one ask), never only a command. About 1,000 tokens; first line is the answer; tables, not prose.

**Never**
- Never infer maturity from industry averages or invent benchmark figures; a dimension without evidence is `[TO BE BASELINED — owner: ___]`.
- Never weight the formula, never rank a row missing any of V, F, D, R, never carry over an earlier score.
- Never schedule scale before measurement exists.

**Which reply**
1. **No current-state evidence** (e.g. "write us an AI strategy, we are a retailer"): ask once, then stop — no scores. Offer this table to fill: `| Input | Your answer |` rows: data platforms · cloud · existing AI/ML in production · AI team and skills · AI policy/governance · strategic priorities (12 months) · executive sponsor and budget envelope · candidate use cases.
2. **Operating-model question only**: answer in tables (≤350 words). Apply `references/operating-models.md`: maturity 1–2 and talent in one team → Central CoE; maturity 2–3, 3+ business units, a platform exists → **Hub-and-spoke**; maturity 4+ with AI engineers in every BU → Federated. Give: `| Model | Verdict | Why |` (chosen + the two rejected); **design decisions** `| Decision | Recommendation |` — reporting line (where the data platform reports, never under one BU), funding (central for platform and lighthouses; chargeback once metered), intake (quarterly review + fast lane), risk gate (tiered: self-certify low, CoE medium, committee high), build vs buy/partner; **precondition: 1–3 AI-capable people per spoke** (talent per spoke) before the hub hands over; **transition triggers** (central → hub-and-spoke: 2+ spokes have trained builders and the platform has self-service onboarding and eval gates; hub-and-spoke → federated: value tracking at level 4, controls tested, spokes pass audits two quarters running).
3. **Full strategy from a description**, in this order: (a) **maturity table** `| Dimension | Score 1–5 | Evidence (from the user's words) |` for all five — data, platform, talent, governance, value — score only what the user's facts support, else `[TO BE BASELINED — owner: ___]`; (b) **"Overall: Level N (= minimum of the evidenced scores); constraining dimension: X"**; (c) operating model chosen + two rejected with reasons; (d) **portfolio** — one row per idea the user counts (e.g. all 12), columns `V | F | D | R | priority = V×F×D÷R | band`; unnamed or unscored ideas keep their row with axes `[TBD at scoring workshop]` and band "unscored"; (e) governance minimum (intake gate, risk tiers, model inventory, review cadence); (f) **roadmap** `| Quarter | Focus | Exit criterion | Owner |` for Q1–Q4 from `references/roadmap-skeleton.md` (Q1 foundations + 1–2 lighthouses with baselines; Q4 operating-model transition decision); (g) ≤5-bullet executive summary.
4. **Use-case CSV attached but no maturity scorecard**: first line asks once for the **maturity scorecard** (`dimension, score_1_to_5, evidence, gap_to_next_level, owner`; `assets/maturity-scorecard.csv`) — `maturity.py` cannot run without it; maturity stays "pending", not inferred. The ranked portfolio may follow.
5. **Files attached**: name the commands — `python3 -I scripts/score_portfolio.py use-cases.csv --out-dir out --org <org> [--previous previous-portfolio.csv]` → `portfolio.csv`, `unscored.csv`, `portfolio.md`; `python3 -I scripts/maturity.py maturity-scorecard.csv --out-dir out --org <org> --target 3 --default-owner "AI CoE lead"` → `maturity.md`, `roadmap.md` — then show the computed result.

**Portfolio procedure — compute row by row from the CSV; show the working table** (`scripts/score_portfolio.py`)
1. A row with any blank V/F/D/R → **unscored** (`missing score(s): …`), not ranked.
2. score = V×F×D÷R (2 decimals). Sort by score desc, tie → lower id first. rank k = 1..n (n = ranked rows).
3. quartile = ceil(k×4÷n) (n = 9: ranks 1–2 → Q1, 3–4 → Q2, 5–6 → Q3, 7–9 → Q4).
4. Band, first match: **Stop** if V≤2 or F=1 or R=5; **Now** if quartile 1, R≤3, D≥3 and owner and baseline named (else Next, "no owner/baseline"); **Next** if quartile 1 with D≤2 or R>3, or quartile 2; else **Later**. Blank owner/baseline/evidence shows `[TO BE BASELINED — owner: AI CoE lead]`.
5. With a previous portfolio.csv: movement = previous rank − rank now (`up N` / `down N` / `same`; `new` if absent before); band before → now (e.g. "UC-003 Now → Next"); list ids ranked before that are now unscored or **no longer in the list**. Computed from the two files only.
Working table: `| rank | id | V | F | D | R | score | quartile | band | reason | prev rank/band | movement |`.

**Maturity procedure** (`scripts/maturity.py`): a score without evidence is not a score → `[TO BE BASELINED — owner: <owner, else AI CoE lead>]`; overall = minimum of the evidenced scores, name the constraining dimension (level names 1 Ad hoc, 2 Emerging, 3 Defined, 4 Managed, 5 Optimizing); gap = below target (default 3) or unevidenced; **one roadmap item per gap**, with owner.

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

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-strategy-coe --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-strategy-coe`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`portfolio.csv`, `portfolio.md`, `maturity.md`, `roadmap.md`); fill the operating-model and governance sections of the roadmap by hand from the references.
