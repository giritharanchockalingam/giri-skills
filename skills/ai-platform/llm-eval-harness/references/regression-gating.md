# Regression Gating

## Gate definition
| Gate | Rule | Typical setting (assumption; set per risk tier) |
|---|---|---|
| Overall pass rate | weighted pass rate ≥ threshold | ≥ 0.85 internal; ≥ 0.90 employee-facing; ≥ 0.95 customer-facing |
| Per-category minimum | each category ≥ its own threshold | ≥ 0.80, higher for critical categories |
| Zero-tolerance | count of zero-tolerance failures = 0 | always |
| Max regression | overall pass rate ≥ baseline − delta | delta = 0.02 |
| Held-out slice | pass rate on held-out ≥ visible-slice − delta | delta = 0.05 (overfitting detector) |
| Cost / latency | mean cost per case and p95 latency within SLO | per SLO |

The runner's `--threshold`, `--category-min`, `--baseline`, `--max-regression` flags implement the first four; the CI job records the baseline artifact.

## CI wiring (GitHub Actions snippet)
```yaml
- name: LLM evals (deterministic)
  run: python3 -I skills/ai-platform/llm-eval-harness/scripts/run_evals.py \
         --golden evals/golden-set.csv --rubric evals/eval-rubric.csv \
         --out evals/scorecard.json --threshold 0.90 --category-min 0.80 \
         --baseline evals/baseline.json --max-regression 0.02
- name: Upload scorecard
  uses: actions/upload-artifact@v4
  with: { name: eval-scorecard, path: evals/scorecard.json }
```
Pytest collection: `pytest skills/ai-platform/llm-eval-harness/scripts/run_evals.py` runs `test_golden_set_gate` with env vars `EVAL_GOLDEN`, `EVAL_RUBRIC`, `EVAL_THRESHOLD`.

## When to run what
| Trigger | Scope |
|---|---|
| Every PR touching prompts, tools, model config | Deterministic full set |
| Release candidate | Deterministic + judge criteria, full set, held-out slice |
| Nightly | Full set against pinned model to detect vendor drift |
| Production | Sampled (2–5%) judge scoring; alert on drop > delta over 24h |

## Baseline management
- `baseline.json` = scorecard of the last accepted release, with `model`, `prompt_version`, `judge_model`, `rubric_version`, `golden_set_version`.
- Update the baseline only in the PR that intentionally changes behavior, with the owner's approval recorded.
- Never compare scores across rubric or judge versions; re-baseline instead.
