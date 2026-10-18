# Playbook — hallucination (incorrect or unsupported output reached users)

## Contain
- Identify the affected feature, prompt version, model version and retrieval index from traces
- Turn on the fallback: route the feature to human review, a safe canned answer, or disable it behind its flag
- Add a temporary output guardrail for the failing pattern (block or flag answers without citations)

## Eradicate
- Reproduce with the exact inputs from the traces; classify the cause: retrieval miss, stale source, prompt regression, model change
- Fix the cause (re-index or correct the source, revert or fix the prompt, pin the previous model version)
- Add the reproducing inputs as regression eval cases before re-enabling

## Recover
- Re-enable the feature through a canary (ai-release-plan) with the regression cases as a gate
- Correct or retract wrong answers already delivered where the product allows it

## Verify
- Regression cases pass and the full eval suite pass rate has not dropped
- Online eval score and negative feedback rate back within SLO for the agreed window (llm-observability)

## References
OWASP Top 10 for LLM Applications 2025: LLM09 Misinformation.
