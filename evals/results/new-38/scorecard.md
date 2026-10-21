# Behavioral eval scorecard
_provider=openai model=gpt-4.1-mini runs=2 seed=42 date=2026-10-20_
_estimated spend: $25.13_

| skill | trigger acc | FP rate | without | with | lift | verdict |
|---|---|---|---|---|---|---|
| build/code-review-runner | 1.00 | 0.00 | 0.12 | 0.12 | 0.00 | BODY |
| build/domain-modeling-runner | 1.00 | 0.00 | 0.14 | 0.29 | 0.14 | BODY |
| build/systematic-debugging-runner | 1.00 | 0.00 | 0.31 | 0.12 | -0.19 | BODY |
| build/webapp-testing-runner | 1.00 | 0.00 | 0.17 | 0.25 | 0.08 | BODY |
| ai-platform/ab-test-analysis | 1.00 | 0.00 | 0.05 | 0.25 | 0.20 | OK |
| ai-platform/ai-adoption-and-literacy | 1.00 | 0.00 | 0.10 | 0.35 | 0.25 | OK |
| ai-platform/ai-bom-license-check | 1.00 | 0.00 | 0.20 | 0.30 | 0.10 | BODY |
| ai-platform/ai-controls-mapping | 1.00 | 0.00 | 0.20 | 0.20 | 0.00 | BODY |
| ai-platform/ai-finops-chargeback | 0.86 | 0.00 | 0.06 | 0.39 | 0.33 | OK |
| ai-platform/ai-incident-runbook | 1.00 | 0.00 | 0.55 | 0.35 | -0.20 | BODY |
| ai-platform/ai-postmortem | 1.00 | 0.00 | 0.39 | 0.61 | 0.22 | OK |
| ai-platform/ai-release-plan | 1.00 | 0.00 | 0.15 | 0.30 | 0.15 | BODY |
| ai-platform/ai-slo-definition | 0.86 | 0.00 | 0.22 | 0.17 | -0.06 | BODY |
| ai-platform/ai-threat-model | 0.67 | 0.00 | 0.06 | 0.38 | 0.31 | DESC |
| ai-platform/ai-transparency-notice | 1.00 | 0.00 | 0.17 | 0.22 | 0.06 | BODY |
| ai-platform/ai-vendor-assessment | 0.79 | 0.00 | 0.39 | 0.22 | -0.17 | BOTH |
| ai-platform/annotation-agreement | 1.00 | 0.00 | 0.35 | 0.45 | 0.10 | BODY |
| ai-platform/bias-fairness-check | 1.00 | 0.00 | 0.05 | 0.30 | 0.25 | OK |
| ai-platform/conversation-design | 0.83 | 0.00 | 0.06 | 0.31 | 0.25 | OK |
| ai-platform/data-contract-validator | 0.75 | 0.00 | 0.20 | 0.20 | 0.00 | BOTH |
| ai-platform/data-readiness-assessment | 0.79 | 0.00 | 0.22 | 0.28 | 0.06 | BOTH |
| ai-platform/dpia | 1.00 | 0.00 | 0.36 | 0.41 | 0.05 | BODY |
| ai-platform/drift-monitor | 0.71 | 0.00 | 0.22 | 0.28 | 0.06 | BOTH |
| ai-platform/eu-ai-act-classifier | 1.00 | 0.00 | 0.19 | 0.44 | 0.25 | OK |
| ai-platform/eval-engineering-runner | 0.71 | 0.00 | 0.22 | 0.11 | -0.11 | BOTH |
| ai-platform/feedback-improvement-loop | 1.00 | 0.00 | 0.00 | 0.25 | 0.25 | OK |
| ai-platform/finetune-dataset-builder | 1.00 | 0.00 | 0.06 | 0.25 | 0.19 | BODY |
| ai-platform/guardrails-config | 0.71 | 0.00 | 0.06 | 0.33 | 0.28 | DESC |
| ai-platform/langchain-rag-runner | 1.00 | 0.00 | 0.33 | 0.22 | -0.11 | BODY |
| ai-platform/langgraph-hitl-runner | 1.00 | 0.00 | 0.06 | 0.12 | 0.06 | BODY |
| ai-platform/langgraph-runner | 1.00 | 0.00 | 0.12 | 0.12 | 0.00 | BODY |
| ai-platform/llm-cost-model | 0.75 | 0.00 | 0.10 | 0.25 | 0.15 | BOTH |
| ai-platform/llm-observability | 0.50 | 0.00 | 0.00 | 0.50 | 0.50 | DESC |
| ai-platform/model-selection | 1.00 | 0.00 | 0.29 | 0.29 | 0.00 | BODY |
| ai-platform/pii-data-inventory | 1.00 | 0.00 | 0.25 | 0.12 | -0.12 | BODY |
| ai-platform/program-raid-status | 1.00 | 0.00 | 0.30 | 0.30 | 0.00 | BODY |
| ai-platform/prompt-spec | 1.00 | 0.00 | 0.00 | 0.29 | 0.29 | OK |
| ai-platform/red-team-suite | 0.67 | 0.00 | 0.00 | 0.29 | 0.29 | DESC |
