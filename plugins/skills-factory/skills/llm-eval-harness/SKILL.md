---
name: llm-eval-harness
description: Use when the user asks "is this agent/LLM app good enough", "build an eval set", "add a regression gate for prompts", "set up LLM-as-judge", or needs to prove quality before release. Produces a golden set, a scoring rubric, an automated pytest-compatible runner (deterministic scorer by default, pluggable LLM judge), a scorecard, and a CI regression gate with thresholds. Not for retrieval-only metrics (rag-pipeline-design has recall@k) or for designing the agent itself (agent-architecture).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: evaluate
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: cases, type: file, required: true, from: "raw cases CSV (input[, expected, must_contain, output …]) or a User:/Assistant: transcript"}
      - {name: rubric, type: csv, required: false, default: "assets/eval-rubric.csv", from: "rubric CSV (references/rubric-design.md)"}
      - {name: outputs, type: csv, required: false, from: "pre-recorded id,output CSV; if absent, outputs come from the `output`/assistant column of cases"}
      - {name: threshold, type: string, required: false, default: "0.9"}
      - {name: existing_golden, type: csv, required: false, from: "golden-set CSV you already have (ids kept; an output column with the release candidate's answers is used for scoring); new cases are merged in, duplicates skipped"}
      - {name: baseline, type: json, required: false, from: "scorecard.json from the last release; adds the per-case comparison (newly failing / passing, new cases)"}
      - {name: max_regression, type: string, required: false, from: "with baseline: fail the gate when the pass rate drops more than this below the baseline, e.g. 0.02; no default"}
    run:
      - {step: golden, kind: script, cmd: "python3 -I scripts/build_golden.py {cases} [--existing {existing_golden} --merge-report {out}/golden-merge.json] --out {out}/golden-set.csv --outputs-out {out}/recorded-outputs.csv"}
      - {step: evals, kind: script, cmd: "python3 -I scripts/run_evals.py --golden {out}/golden-set.csv --rubric {rubric} --outputs {outputs} --out {out}/scorecard.json --threshold {threshold} [--baseline {baseline}] [--max-regression {max_regression}] --skip-judge", stdout: "{out}/scorecard.txt", skip_if_missing: [outputs]}
      - {step: evals-recorded, kind: script, cmd: "python3 -I scripts/run_evals.py --golden {out}/golden-set.csv --rubric {rubric} --outputs {out}/recorded-outputs.csv --out {out}/scorecard.json --threshold {threshold} [--baseline {baseline}] [--max-regression {max_regression}] --skip-judge", stdout: "{out}/scorecard.txt", skip_if_present: [outputs]}
    outputs:
      - {path: "{out}/golden-set.csv", checks: [exists, csv:[id,category,difficulty,input,must_contain,must_not_contain,source]]}
      - {path: "{out}/scorecard.json", checks: [exists, json]}
      - {path: "{out}/scorecard.txt", checks: [exists, contains:"GATE"]}
    modes:
      new:      {case: agent-happy-path, bring: "real question-and-answer examples from your help desk"}
      existing: {case: agent-mode-existing, bring: "your golden set, new production cases and last release's scorecard"}
---

# LLM Eval Harness

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/llm-eval-harness --input <name>=<value> … --out <dir>` (see `--explain ai-platform/llm-eval-harness`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

## Starting points
- **New** — turn raw cases or a transcript into a golden set and run the regression gate on recorded outputs.
- **Existing** — pass your current golden set as `existing_golden` (with the candidate's outputs in an `output` column), new production cases as `cases`, and last release's scorecard as `baseline` (optionally `max_regression`): the set is extended without renumbering (`golden-merge.json`) and the scorecard adds a per-case comparison (newly failing, newly passing, new cases).

## When to use
- Before first release of any LLM feature or agent; before every prompt/model/tool change thereafter.
- Answering "is it good enough" with numbers instead of demos.
- NOT for: retrieval tuning alone (`rag-pipeline-design`), load testing, security pen-testing.

## Inputs required
| Input | Required | Source |
|---|---|---|
| The system under test: how to call it (function, HTTP endpoint, CLI) and its input/output shape | yes | user / repo |
| What "good" means: the task definition and the failure types the owner fears most | yes | user |
| Real examples: ≥ 30 inputs with expected outputs or acceptance notes | yes | user / logs; if absent, ask — synthetic cases are labeled and capped at 30% of the set |
| Risk tier (internal / employee-facing / customer-facing / regulated) | yes | user |
| Release cadence and CI system | no | repo |

If the system interface or the real examples are missing, ask once.

## Procedure
1. Read `../../shared/quality-bar.md` and `../../shared/token-efficiency.md`.
2. **Build the golden set** with `references/golden-set.md` into `assets/golden-set.csv`: id, input, expected (or acceptance keywords/regex), category, difficulty, must-not-contain, source, weight.
3. **Design the rubric** with `references/rubric-design.md` into `assets/eval-rubric.csv`: criterion, definition, scale, pass threshold, scoring method (deterministic / judge / human), weight.
4. **Wire the runner.** Copy `scripts/run_evals.py`; implement `call_system(input) -> output` for the system under test. Default scoring is deterministic (keywords, regex, must-not-contain, exact match, JSON validity). Add an LLM judge only for criteria that cannot be scored deterministically, following `references/llm-as-judge.md`.
5. **Run baseline.** `python3 -I scripts/run_evals.py --golden assets/golden-set.csv --rubric assets/eval-rubric.csv --out scorecard.json`. Record the baseline per category.
6. **Set the gate** with `references/regression-gating.md`: overall threshold, per-category minimums, zero-tolerance checks (safety, must-not-contain), and max regression vs baseline. Add the runner to CI (pytest collects it).
7. **Report** the scorecard: table by category, failures with ids, gate result, recommended fixes.
8. Run the self-check.

## Output
- `assets/golden-set.csv`, `assets/eval-rubric.csv` filled; `scripts/run_evals.py` adapted; `scorecard.json`; CI job snippet.
- Scorecard table in the reply: category | n | pass rate | mean score | gate.

## Self-check
- [ ] ≥ 30 cases; synthetic share ≤ 30% and labeled
- [ ] Every rubric criterion has a scoring method and threshold
- [ ] Deterministic checks used wherever possible; judge only where needed, with calibration plan
- [ ] Zero-tolerance checks defined for the risk tier
- [ ] Gate fails the build on threshold or regression breach
- [ ] Baseline recorded with model/prompt version
- [ ] No quality claims without the scorecard

## References
- `references/golden-set.md` — construction, coverage, sourcing, maintenance
- `references/rubric-design.md` — criteria, scales, thresholds, weights
- `references/llm-as-judge.md` — pitfalls and controls
- `references/regression-gating.md` — thresholds, CI wiring, drift monitoring
- `scripts/run_evals.py` — runner (pytest-compatible)
