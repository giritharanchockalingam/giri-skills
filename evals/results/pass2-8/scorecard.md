# Behavioral eval scorecard
_provider=openai model=gpt-4.1-mini runs=2 seed=42 date=2026-10-21_
_estimated spend: $4.70_

| skill | trigger acc | FP rate | without | with | lift | verdict |
|---|---|---|---|---|---|---|
| build/code-review-runner | 1.00 | 0.00 | 0.88 | 1.00 | 0.12 | BODY |
| ai-platform/ai-controls-mapping | 1.00 | 0.00 | 0.10 | 0.70 | 0.60 | OK |
| ai-platform/ai-vendor-assessment | 0.86 | 0.00 | 0.50 | 0.50 | 0.00 | BODY |
| ai-platform/data-readiness-assessment | 1.00 | 0.00 | 0.50 | 0.67 | 0.17 | BODY |
| ai-platform/finetune-dataset-builder | 1.00 | 0.00 | 0.38 | 0.69 | 0.31 | OK |
| ai-platform/langchain-rag-runner | 1.00 | 0.00 | 0.50 | 0.89 | 0.39 | OK |
| ai-platform/langgraph-runner | 1.00 | 0.00 | 0.44 | 0.88 | 0.44 | OK |
| ai-platform/program-raid-status | 1.00 | 0.00 | 0.50 | 0.60 | 0.10 | BODY |
