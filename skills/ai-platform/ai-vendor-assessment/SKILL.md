---
name: ai-vendor-assessment
description: Use when the user must choose between AI vendors, model providers or AI platforms (optionally against building in-house) — "compare these AI vendors", "build vs buy for our assistant", "score the platform shortlist", "does the ranking hold if we change the weights", "third-party AI risk review". Produces scores.csv (weighted score, rank, completeness, red flags), sensitivity.csv (each criterion weight ±20%, whether the top option changes) and vendor-report.md (Summary, Scores, Sensitivity, Third-party risk, Recommendation, Method) from an options score CSV, a criteria weights CSV and optional answers to a shipped third-party AI risk questionnaire (training on customer data, retention, residency, sub-processors, SOC 2, ISO/IEC 27001, ISO/IEC 42001, model change notice, incident SLA, IP indemnity, exit). Not for picking a model on eval and token-cost facts (model-selection), API cost forecasting (llm-cost-model) or contract drafting.
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

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-vendor-assessment --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-vendor-assessment`). Report the `run.json` results; do not hand-write the deliverables the script produces (`scores.csv`, `sensitivity.csv`, `vendor-report.md`). "No clear winner" is a finding, not a failure (exit 0) unless `require_clear_winner=true`, which makes it a gate (exit 1, outputs still written).

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
1. Read `../../../shared/quality-bar.md`.
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
