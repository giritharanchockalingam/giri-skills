# Behavioral eval scorecard
_provider=dry model=claude-sonnet-4-5 date=2026-10-18_
_agent mode: 208 cases run with scripts/run_skill.py; verdict Works >= 0.9, Partial >= 0.5, else Broken; blank = no agent cases_

| skill | trigger acc | FP rate | without | with | lift | verdict | agent pass | agent verdict |
|---|---|---|---|---|---|---|---|---|
| presales/account-plan |  |  |  |  |  |  | 1.00 | Works |
| presales/client-research-brief |  |  |  |  |  |  | 1.00 | Works |
| presales/competitive-positioning |  |  |  |  |  |  | 1.00 | Works |
| presales/discovery-interview |  |  |  |  |  |  | 1.00 | Works |
| presales/effort-estimator |  |  |  |  |  |  | 1.00 | Works |
| presales/exec-deck-redline |  |  |  |  |  |  | 1.00 | Works |
| presales/integration-migration-assessor |  |  |  |  |  |  | 1.00 | Works |
| presales/orals-prep |  |  |  |  |  |  | 1.00 | Works |
| presales/proposal-writer |  |  |  |  |  |  | 1.00 | Works |
| presales/rfp-compliance-matrix |  |  |  |  |  |  | 1.00 | Works |
| presales/solution-architecture-doc |  |  |  |  |  |  | 1.00 | Works |
| presales/sow-drafter |  |  |  |  |  |  | 1.00 | Works |
| presales/value-case-builder |  |  |  |  |  |  | 1.00 | Works |
| build/ci-cd-vercel-github |  |  |  |  |  |  | 1.00 | Works |
| build/code-review-runner |  |  |  |  |  |  | 1.00 | Works |
| build/domain-modeling-runner |  |  |  |  |  |  | 1.00 | Works |
| build/handoff-and-thread-close |  |  |  |  |  |  | 1.00 | Works |
| build/multi-tenant-saas-patterns |  |  |  |  |  |  | 1.00 | Works |
| build/nextjs-enterprise-conventions |  |  |  |  |  |  | 1.00 | Works |
| build/observability-setup |  |  |  |  |  |  | 1.00 | Works |
| build/product-spec-prd |  |  |  |  |  |  | 1.00 | Works |
| build/project-bootstrap |  |  |  |  |  |  | 1.00 | Works |
| build/safe-fix |  |  |  |  |  |  | 1.00 | Works |
| build/security-review |  |  |  |  |  |  | 1.00 | Works |
| build/spec-to-plan |  |  |  |  |  |  | 1.00 | Works |
| build/supabase-schema-rls |  |  |  |  |  |  | 1.00 | Works |
| build/systematic-debugging-runner |  |  |  |  |  |  | 1.00 | Works |
| build/test-strategy-tdd |  |  |  |  |  |  | 1.00 | Works |
| build/webapp-testing-runner |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/agent-architecture |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/ai-governance-risk |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/ai-incident-runbook |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/ai-release-plan |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/ai-strategy-coe |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/ai-use-case-canvas |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/bias-fairness-check |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/data-readiness-assessment |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/eval-engineering-runner |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/feedback-improvement-loop |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/finetune-dataset-builder |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/guardrails-config |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/infra-gpu-sizing |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/langchain-rag-runner |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/langgraph-hitl-runner |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/langgraph-runner |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/llm-cost-model |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/llm-eval-harness |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/llm-observability |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/mcp-server-builder |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/model-selection |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/pii-data-inventory |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/prompt-spec |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/rag-pipeline-design |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/red-team-suite |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/slm-demo-builder |  |  |  |  |  |  | 1.00 | Works |
| career/application-tracker |  |  |  |  |  |  | 1.00 | Works |
| career/interview-prep |  |  |  |  |  |  | 1.00 | Works |
| career/jd-fit-scorer |  |  |  |  |  |  | 1.00 | Works |
| career/offer-evaluator |  |  |  |  |  |  | 1.00 | Works |
| career/outreach-and-followup |  |  |  |  |  |  | 1.00 | Works |
| career/resume-tailor |  |  |  |  |  |  | 1.00 | Works |
