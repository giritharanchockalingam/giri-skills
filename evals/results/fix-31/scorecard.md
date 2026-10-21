# Behavioral eval scorecard
_provider=openai model=gpt-4.1-mini runs=2 seed=42 date=2026-10-21_
_estimated spend: $20.50_

| skill | trigger acc | FP rate | without | with | lift | verdict |
|---|---|---|---|---|---|---|
| presales/effort-estimator | 0.88 | 0.00 | 0.12 | 0.25 | 0.12 | BODY |
| build/code-review-runner | 1.00 | 0.00 | 0.12 | 0.12 | 0.00 | BODY |
| build/domain-modeling-runner | 1.00 | 0.00 | 0.29 | 0.43 | 0.14 | BODY |
| build/systematic-debugging-runner | 1.00 | 0.00 | 0.25 | 0.38 | 0.12 | BODY |
| build/webapp-testing-runner | 1.00 | 0.00 | 0.08 | 0.33 | 0.25 | OK |
| ai-platform/ai-bom-license-check | 1.00 | 0.00 | 0.15 | 0.60 | 0.45 | OK |
| ai-platform/ai-controls-mapping | 0.83 | 0.00 | 0.15 | 0.30 | 0.15 | BODY |
| ai-platform/ai-incident-runbook | 1.00 | 0.00 | 0.50 | 0.60 | 0.10 | BODY |
| ai-platform/ai-release-plan | 1.00 | 0.00 | 0.10 | 0.50 | 0.40 | OK |
| ai-platform/ai-slo-definition | 0.86 | 0.00 | 0.17 | 0.56 | 0.39 | OK |
| ai-platform/ai-threat-model | 0.83 | 0.00 | 0.12 | 0.44 | 0.31 | OK |
| ai-platform/ai-transparency-notice | 1.00 | 0.00 | 0.17 | 0.56 | 0.39 | OK |
| ai-platform/ai-vendor-assessment | 0.86 | 0.00 | 0.44 | 0.50 | 0.06 | BODY |
| ai-platform/annotation-agreement | 1.00 | 0.00 | 0.40 | 0.50 | 0.10 | BODY |
| ai-platform/data-contract-validator | 0.88 | 0.00 | 0.25 | 0.50 | 0.25 | OK |
| ai-platform/data-readiness-assessment | 1.00 | 0.00 | 0.22 | 0.39 | 0.17 | BODY |
| ai-platform/dpia | 1.00 | 0.00 | 0.32 | 0.55 | 0.23 | OK |
| ai-platform/drift-monitor | 0.86 | 0.00 | 0.17 | 0.61 | 0.44 | OK |
| ai-platform/eval-engineering-runner | 1.00 | 0.00 | 0.28 | 0.22 | -0.06 | BODY |
| ai-platform/finetune-dataset-builder | 1.00 | 0.00 | 0.19 | 0.19 | 0.00 | BODY |
| ai-platform/guardrails-config | 1.00 | 0.00 | 0.06 | 0.56 | 0.50 | OK |
| ai-platform/infra-gpu-sizing | 1.00 | 0.00 | 0.25 | 0.82 | 0.57 | OK |
| ai-platform/langchain-rag-runner | 1.00 | 0.00 | 0.33 | 0.44 | 0.11 | BODY |
| ai-platform/langgraph-hitl-runner | 1.00 | 0.00 | 0.06 | 0.25 | 0.19 | BODY |
| ai-platform/langgraph-runner | 1.00 | 0.00 | 0.19 | 0.19 | 0.00 | BODY |
| ai-platform/llm-cost-model | 0.88 | 0.00 | 0.20 | 0.25 | 0.05 | BODY |
| ai-platform/llm-observability | 0.88 | 0.00 | 0.07 | 0.64 | 0.57 | OK |
| ai-platform/model-selection | 1.00 | 0.00 | 0.21 | 0.57 | 0.36 | OK |
| ai-platform/pii-data-inventory | 1.00 | 0.00 | 0.25 | 0.25 | 0.00 | BODY |
| ai-platform/program-raid-status | 1.00 | 0.00 | 0.20 | 0.25 | 0.05 | BODY |
| ai-platform/red-team-suite | 1.00 | 0.00 | 0.07 | 0.29 | 0.21 | OK |
