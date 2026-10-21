# Behavioral eval scorecard
_provider=openai model=gpt-4.1-mini runs=2 seed=42 date=2026-10-21_
_estimated spend: $11.47_

| skill | trigger acc | FP rate | without | with | lift | verdict |
|---|---|---|---|---|---|---|
| presales/effort-estimator | 0.88 | 0.00 | 0.20 | 0.42 | 0.22 | OK |
| build/code-review-runner | 1.00 | 0.00 | 0.81 | 0.94 | 0.12 | BODY |
| build/domain-modeling-runner | 1.00 | 0.00 | 0.71 | 1.00 | 0.29 | OK |
| build/security-review | 0.81 | 0.00 | 0.42 | 0.81 | 0.38 | OK |
| build/systematic-debugging-runner | 1.00 | 0.00 | 0.62 | 1.00 | 0.38 | OK |
| ai-platform/ai-controls-mapping | 1.00 | 0.00 | 0.20 | 0.35 | 0.15 | BODY |
| ai-platform/ai-incident-runbook | 1.00 | 0.00 | 0.60 | 0.90 | 0.30 | OK |
| ai-platform/ai-vendor-assessment | 0.86 | 0.00 | 0.39 | 0.39 | 0.00 | BODY |
| ai-platform/annotation-agreement | 1.00 | 0.00 | 0.40 | 0.65 | 0.25 | OK |
| ai-platform/data-readiness-assessment | 1.00 | 0.00 | 0.44 | 0.61 | 0.17 | BODY |
| ai-platform/eval-engineering-runner | 1.00 | 0.00 | 0.39 | 0.67 | 0.28 | OK |
| ai-platform/finetune-dataset-builder | 1.00 | 0.00 | 0.50 | 0.44 | -0.06 | BODY |
| ai-platform/langchain-rag-runner | 1.00 | 0.00 | 0.61 | 0.67 | 0.06 | BODY |
| ai-platform/langgraph-hitl-runner | 1.00 | 0.00 | 0.19 | 0.44 | 0.25 | OK |
| ai-platform/langgraph-runner | 1.00 | 0.00 | 0.56 | 0.56 | 0.00 | BODY |
| ai-platform/llm-cost-model | 0.88 | 0.00 | 0.30 | 0.80 | 0.50 | OK |
| ai-platform/pii-data-inventory | 1.00 | 0.00 | 0.38 | 0.62 | 0.25 | OK |
| ai-platform/program-raid-status | 1.00 | 0.00 | 0.40 | 0.35 | -0.05 | BODY |
