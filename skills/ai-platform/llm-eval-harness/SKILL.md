---
name: llm-eval-harness
description: Use when the user asks "is this agent/LLM app good enough", "build an eval set", "add a regression gate for prompts", "set up LLM-as-judge", or needs to prove quality before release. Produces a golden set, a scoring rubric, an automated pytest-compatible runner (deterministic scorer by default, pluggable LLM judge), a scorecard, and a CI regression gate with thresholds. Not for retrieval-only metrics (rag-pipeline-design has recall@k) or for designing the agent itself (agent-architecture).
license: MIT
metadata:
  domain: ai-platform
  version: 0.1.0
  author: giri-skills
---

# LLM Eval Harness

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
1. Read `../../../shared/quality-bar.md` and `../../../shared/token-efficiency.md`.
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
