# Behavioral eval scorecard
_provider=dry model=claude-sonnet-4-5 date=2026-10-17_
_agent mode: 36 cases run with scripts/run_skill.py; verdict Works >= 0.9, Partial >= 0.5, else Broken; blank = no agent cases_

| skill | trigger acc | FP rate | without | with | lift | verdict | agent pass | agent verdict |
|---|---|---|---|---|---|---|---|---|
| presales/account-plan |  |  |  |  |  |  |  |  |
| presales/client-research-brief |  |  |  |  |  |  | 1.00 | Works |
| presales/competitive-positioning |  |  |  |  |  |  |  |  |
| presales/discovery-interview |  |  |  |  |  |  |  |  |
| presales/effort-estimator |  |  |  |  |  |  | 1.00 | Works |
| presales/exec-deck-redline |  |  |  |  |  |  |  |  |
| presales/integration-migration-assessor |  |  |  |  |  |  | 1.00 | Works |
| presales/orals-prep |  |  |  |  |  |  |  |  |
| presales/proposal-writer |  |  |  |  |  |  |  |  |
| presales/rfp-compliance-matrix |  |  |  |  |  |  | 1.00 | Works |
| presales/solution-architecture-doc |  |  |  |  |  |  |  |  |
| presales/sow-drafter |  |  |  |  |  |  |  |  |
| presales/value-case-builder |  |  |  |  |  |  |  |  |
| build/ci-cd-vercel-github |  |  |  |  |  |  |  |  |
| build/handoff-and-thread-close |  |  |  |  |  |  |  |  |
| build/multi-tenant-saas-patterns |  |  |  |  |  |  |  |  |
| build/nextjs-enterprise-conventions |  |  |  |  |  |  |  |  |
| build/observability-setup |  |  |  |  |  |  |  |  |
| build/product-spec-prd |  |  |  |  |  |  |  |  |
| build/project-bootstrap |  |  |  |  |  |  | 1.00 | Works |
| build/safe-fix |  |  |  |  |  |  |  |  |
| build/security-review |  |  |  |  |  |  |  |  |
| build/spec-to-plan |  |  |  |  |  |  |  |  |
| build/supabase-schema-rls |  |  |  |  |  |  | 1.00 | Works |
| build/test-strategy-tdd |  |  |  |  |  |  |  |  |
| ai-platform/agent-architecture |  |  |  |  |  |  |  |  |
| ai-platform/ai-governance-risk |  |  |  |  |  |  |  |  |
| ai-platform/ai-strategy-coe |  |  |  |  |  |  |  |  |
| ai-platform/ai-use-case-canvas |  |  |  |  |  |  |  |  |
| ai-platform/infra-gpu-sizing |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/llm-eval-harness |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/mcp-server-builder |  |  |  |  |  |  |  |  |
| ai-platform/rag-pipeline-design |  |  |  |  |  |  | 1.00 | Works |
| ai-platform/slm-demo-builder |  |  |  |  |  |  |  |  |
| career/application-tracker |  |  |  |  |  |  | 1.00 | Works |
| career/interview-prep |  |  |  |  |  |  |  |  |
| career/jd-fit-scorer |  |  |  |  |  |  | 1.00 | Works |
| career/offer-evaluator |  |  |  |  |  |  | 1.00 | Works |
| career/outreach-and-followup |  |  |  |  |  |  |  |  |
| career/resume-tailor |  |  |  |  |  |  |  |  |
