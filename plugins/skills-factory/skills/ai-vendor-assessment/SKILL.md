---
name: ai-vendor-assessment
description: Use when the user must choose between AI vendors, model providers or AI platforms (optionally against building in-house) — "compare these AI vendors", "build vs buy for our assistant", "score the platform shortlist", "does the ranking hold if we change the weights", "third-party AI risk review", "gate the vendor decision: fail unless there is a clear winner", "a vendor now trains on customer data by default". Produces scores.csv (weighted score, rank, completeness, red flags), sensitivity.csv (each criterion weight ±20%, whether the top option changes) and vendor-report.md (Summary, Scores, Sensitivity, Third-party risk, Recommendation, Method) from an options score CSV, a criteria weights CSV and optional answers to a shipped third-party AI risk questionnaire (11 questions: training on customer data, retention, residency, SOC 2, ISO/IEC 42001, exit and more). Not for picking a model on eval and token-cost facts (model-selection), API cost forecasting (llm-cost-model) or contract drafting.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: strategy
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-happy-path, bring: "a shortlist of vendors, your criteria and their risk answers"}
      existing: {case: agent-mode-existing, bring: "this year's scores plus the last assessment's results"}
    inputs:
      - {name: options, type: csv, required: true, from: "scores option,criterion,score,source (layout: assets/options-template.csv; score 1-5, blank = missing)"}
      - {name: criteria, type: csv, required: true, from: "criterion,weight,description (layout: assets/criteria-template.csv; weights any scale, normalised)"}
      - {name: risk, type: csv, required: false, from: "option,question_id,answer,evidence answering assets/third-party-ai-risk-questions.csv (layout: assets/risk-template.csv; unknown = gap, n/a = not applicable); without it risk is not assessed"}
      - {name: questions, type: csv, required: false, from: "your own copy of assets/third-party-ai-risk-questions.csv with policy thresholds (default: the shipped file)"}
      - {name: previous, type: csv, required: false, from: "scores.csv from the last assessment (e.g. at renewal); the report adds score, rank and red-flag changes"}
      - {name: require_clear_winner, type: flag, required: false, flag: "--require-clear-winner", from: "true to fail the run (exit 1) when there is no clear winner"}
    run:
      - {step: assess, kind: script, cmd: "python3 -I scripts/vendor_assess.py --options {options} --criteria {criteria} [--risk {risk}] [--questions {questions}] {require_clear_winner} [--previous {previous}] --out-dir {out}"}
    outputs:
      - {path: "{out}/scores.csv", checks: [exists, "csv:[option,weighted_score,rank,complete,red_flags]", "csv_rows:complete~^(yes|no)$", csv_rows:red_flags!empty, cmd:"python3 -I scripts/vendor_assess.py --verify {path}"]}
      - {path: "{out}/sensitivity.csv", checks: [exists, "csv:[criterion,change,weight_before,weight_after,top_option,top_changed]", "csv_rows:top_changed~^(yes|no)$", cmd:"python3 -I scripts/vendor_assess.py --verify {path}"]}
      - {path: "{out}/vendor-report.md", checks: [exists, sections:["Summary","Scores","Sensitivity","Third-party risk","Recommendation","Method"], no_unowned_tbd, contains:"normalised to 1.000"]}
---

# AI Vendor Assessment (weighted scoring + third-party AI risk)

## In a conversation: score the vendors now
The reply **is the assessment** (or its skeleton), never only a request for files. Replies are short (about 900 tokens): no preamble, tables over prose, risk shown as red flags and unanswered ids only (not 11 rows per option). The first three lines are always:
1. `Recommendation: <option> | no clear winner | pending — <reason>`
2. `Run: python3 -I scripts/vendor_assess.py --options <options.csv> --criteria <criteria.csv> [--risk <risk.csv>] [--previous <scores.csv>] [--require-clear-winner] --out-dir out` → `scores.csv`, `sensitivity.csv`, `vendor-report.md` (use the case's flags).
3. `Limits: a decision aid, not a contract or legal review; vendor claims are recorded, not verified; a missing score is never imputed.`

**Never**
- Never invent, propose or "sensibly" fill weights, even when asked ("use whatever weights make sense"). No criteria file → line 1 `Recommendation: pending — criteria weights not provided; the run stops (exit 2)`, then decline in one sentence ("Weights must come from the decision owner; I will not invent them") and ask once: "Please send the criteria weights CSV `criterion,weight,description` signed off by the decision owner (sponsor)." Show the supplied scores and completeness only; no weighted score, rank or sensitivity.
- Never impute a blank score: that option is `complete = no`, no weighted score, no rank, excluded from the recommendation; gap `<criterion> [TO BE BASELINED — owner: Procurement lead]`.
- Never assume a risk answer ("assume the big vendors are compliant"): risk `not assessed [TO BE BASELINED — owner: Third-party risk manager]`; recommendation `Conditional on a third-party risk review [TO BE BASELINED — owner: Third-party risk manager].`
- Never treat `unknown`/blank/no row as a red flag (it is unanswered, owner Third-party risk manager); `n/a` is not applicable. Never use last year's scores in today's scores.

**Procedure — compute from the supplied rows, writing every product out; never estimate**
1. Raw weights r_c and their sum R (weights normalised to 1.000: w_c = r_c ÷ R).
2. Complete option = a 1-5 score on every criterion. Score outside 1-5, unknown criterion or duplicate row → **stops (exit 2)**.
3. Numerator N = Σ r_c × score_c, every term written; weighted score = N ÷ R (3 dp). Worked example (`references/method.md`): weights 40/25/20/15, scores 5,3,4,4 → N = 40×5 + 25×3 + 20×4 + 15×4 = 200 + 75 + 80 + 60 = 415; 415 ÷ 100 = **4.150**. Match each score to its criterion by name, not by row order. Rank by score descending; equal scores share a rank.
4. Sensitivity (2 runs per criterion: ×0.8, ×1.2 on that raw weight only). Let D = N_top − N_other for each other complete option. Under criterion c and factor f: D' = D + (f − 1) × r_c × (score_top,c − score_other,c); new sum R' = R + (f − 1) × r_c. The top is unchanged when every D' > 0 (`top_changed = no`); D' ≤ 0 → `yes`. Margin to the runner-up = min D' ÷ R'. Worked example (method.md): answer_quality 40 × 0.8 → R' = 92; Fabrikam 375/92 = 4.076 vs Tailspin 353/92 = 3.837; D' = 22, margin 0.239, top unchanged. Rank stability % = runs with `no` ÷ (2 × criteria) × 100 (state "n of N runs").
5. Red flags — test every answer against its rule and write the test, e.g. `TPR-02 90 > 30 → RED`, `TPR-02 30 > 30? no`: TPR-01 eq:yes · TPR-02 retention days gt:30 · TPR-03 eq:no · TPR-04 eq:no · TPR-05 eq:no · TPR-06 eq:no · TPR-07 eq:no (`in_progress` not red) · TPR-08 change notice days lt:30 · TPR-09 incident hours gt:72 · TPR-10 eq:no · TPR-11 eq:no. `unknown`/blank/missing = unanswered, not red.
6. Recommendation: clear winner = top complete option, not tied, with no red flags, first in every sensitivity run → `Recommendation: <option> (weighted score x.xxx)`. Else `**No clear winner.** Reasons: …` (tie / "top-scoring X has red flags: TPR-nn" / "the top option changes under <criterion> <±20%>") and "Highest-scoring option without red flags: Y (score)". With `--require-clear-winner` and no clear winner, write "the run **stops (exit 1)**; outputs still written"; otherwise exit 0. No risk file → conditional (see Never).
7. Previous `scores.csv`: per option score then → now, change = now − then (signed, 3 dp), rank then → now, red flags raised/cleared; absent last time = `new option`; only in the previous file = `no longer assessed`.

**Reply layout after the three lines**
1. **Scores** working table: `option | N = Σ r×score (terms shown) | weighted score | rank | complete | red flags | unanswered`.
2. **Sensitivity**: one line per run `criterion ±20%: R' | D' per rival | top | margin | top_changed`, then `Rank stability: x% (n of N runs)`.
3. **Third-party risk**: per option, red-flag tests that fired, unanswered ids with owner.
4. **Recommendation** (as step 6), **Changes since last assessment** (when `previous`), **Method** (weights normalised to 1.000, raw sum R).

**No files in the conversation** (vendors named, no scores/weights shown): line 1 `Recommendation: pending — scores and weights not yet supplied`, lines 2–3 as above, then these sections, each one line, then the ask:
- **Weighted scores**: per option `[TO BE BASELINED — owner: Procurement lead]`; computed as Σ normalised weight × score (1-5) on complete options only — a missing score is never imputed.
- **±20% sensitivity and rank stability**: each criterion weight ×0.8 and ×1.2, renormalised; reports whether the winner holds and rank stability %.
- **Red flags (third-party AI risk questionnaire, 11 questions, `assets/third-party-ai-risk-questions.csv`)**: training on customer data, retention > 30 days, residency, sub-processors, SOC 2, ISO/IEC 27001, ISO/IEC 42001, model-change notice < 30 days, incident notice > 72 hours, IP indemnity, exit — per option `[TO BE BASELINED — owner: Third-party risk manager]`.
- Ask once, one list: the scores CSV with a source per score (`option,criterion,score,source`); the criteria weights CSV from the decision owner (`criterion,weight,description`); the risk answers (`option,question_id,answer,evidence`).

**Choosing an LLM on eval scores, token prices and latency**: line 1 routes it to `model-selection`; offer this skill for vendor, contract and third-party risk comparison.

## Starting points
- **New:** a shortlist scored on your weighted criteria, with risk answers, gives the ranking, sensitivity and red flags before procurement.
- **Existing:** add the `scores.csv` from the last assessment (`previous`), e.g. at renewal; the report adds each option's score and rank then and now, red flags raised or cleared, and options new or no longer assessed.

## When to use
- ADLC strategy stage: a shortlist of AI vendors, platforms or providers (and possibly an in-house build) must be compared on agreed criteria before procurement.
- "Does the winner survive if we weight cost higher?" — the ±20% sensitivity answers it per criterion.
- Third-party AI risk screen before contract: red flags on data use, retention, residency, assurance, change notice, incident SLA, indemnity and exit.
- NOT for: choosing a model from eval scores, prices and latency (`model-selection`), forecasting token spend (`llm-cost-model`), legal contract review or drafting, or verifying vendor certificates (inspect the reports themselves).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `options` — option, criterion, score 1–5, source | yes | evaluation team; one row per option × criterion | run stops (exit 2), asks once |
| `criteria` — criterion, weight, description | yes | decision owner (sponsor) | run stops (exit 2), asks once |
| `risk` — option, question_id, answer, evidence | no | Third-party risk manager from vendor responses | risk "not assessed" `[TO BE BASELINED — owner: Third-party risk manager]`; recommendation is conditional |
| `questions` — questionnaire with thresholds | no | Third-party risk manager (copy the shipped file) | shipped defaults (30-day retention, 30-day change notice, 72-hour incident notice) |
| `require_clear_winner` — true/false | no | decision owner | false: "no clear winner" exits 0 |

A blank score is missing: the option is marked incomplete, excluded from ranking and recommendation, and the gap is `[TO BE BASELINED — owner: Procurement lead]`. A score outside 1–5, an unknown criterion or a duplicate row stops the run (exit 2).

## Procedure
1. Read `../../shared/quality-bar.md`.
2. Agree criteria and weights with the decision owner before scoring; record a source for every score.
3. Send vendors `assets/third-party-ai-risk-questions.csv`; record answers (and `n/a` for a build option) in the risk CSV.
4. Run the agent. `scripts/vendor_assess.py` normalises weights, scores complete options, runs ±20% sensitivity per criterion and applies the red-flag rules (`references/method.md`).
5. If there is no clear winner, take the stated reasons to the decision owner (re-score, renegotiate terms, or re-weight) and re-run.
6. Run the self-check.

## Output
- `scores.csv` — `option, weighted_score, rank, complete, red_flags, missing_criteria, risk_unanswered` (ranked complete options first, then incomplete ones).
- `sensitivity.csv` — `criterion, change, weight_before, weight_after, top_option, top_score, runner_up, margin, top_changed` (two rows per criterion).
- `vendor-report.md` — **Summary**, **Scores** (with score matrix), **Sensitivity**, **Third-party risk**, **Recommendation**, **Method**.

## Self-check
- [ ] Every score has a source; no score was imputed
- [ ] Weights normalisation is stated
- [ ] The recommendation is a complete option with no red flags that stays first under every ±20% change — or "no clear winner" with reasons
- [ ] Unanswered risk questions and incomplete options name an owner
- [ ] Limits stated: decision aid, not a legal or contract review; vendor claims not verified

## References
- `references/method.md` — scoring, ranking, sensitivity, red-flag and recommendation rules
- `references/sources.md` — standards named in the questionnaire, with URLs and dates checked
- `assets/third-party-ai-risk-questions.csv` — 11 questions with answer types and red-flag rules
- `assets/options-template.csv`, `assets/criteria-template.csv`, `assets/risk-template.csv` — input layouts
- `scripts/vendor_assess.py` — scorer and `--verify` mode (argparse; stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-vendor-assessment --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-vendor-assessment`). Report the `run.json` results; do not hand-write the deliverables the script produces (`scores.csv`, `sensitivity.csv`, `vendor-report.md`). "No clear winner" is a finding, not a failure (exit 0) unless `require_clear_winner=true`, which makes it a gate (exit 1, outputs still written).
