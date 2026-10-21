# Behavioral eval scorecard
_provider=openai model=gpt-4.1-mini runs=2 seed=42 date=2026-10-21_
_estimated spend: $12.41_

| skill | trigger acc | FP rate | without | with | lift | verdict |
|---|---|---|---|---|---|---|
| presales/account-plan | 0.71 | 0.00 | 0.12 | 0.35 | 0.24 | DESC |
| presales/client-research-brief | 1.00 | 0.00 | 0.38 | 0.53 | 0.15 | BODY |
| presales/competitive-positioning | 0.86 | 0.00 | 0.35 | 0.82 | 0.47 | OK |
| presales/exec-deck-redline | 1.00 | 0.00 | 0.21 | 0.45 | 0.24 | OK |
| presales/orals-prep | 0.86 | 0.00 | 0.09 | 0.38 | 0.29 | OK |
| presales/rfp-compliance-matrix | 1.00 | 0.00 | 0.06 | 0.36 | 0.31 | OK |
| presales/sow-drafter | 1.00 | 0.00 | 0.22 | 0.53 | 0.31 | OK |
| build/ci-cd-vercel-github | 1.00 | 0.00 | 0.25 | 0.71 | 0.46 | OK |
| build/nextjs-enterprise-conventions | 1.00 | 0.00 | 0.36 | 0.57 | 0.21 | OK |
| build/observability-setup | 1.00 | 0.00 | 0.17 | 0.63 | 0.47 | OK |
| build/safe-fix | 1.00 | 0.00 | 0.12 | 0.69 | 0.56 | OK |
| build/security-review | 0.88 | 0.00 | 0.35 | 0.54 | 0.19 | BODY |
| build/spec-to-plan | 1.00 | 0.00 | 0.25 | 0.71 | 0.46 | OK |
| ai-platform/ai-use-case-canvas | 1.00 | 0.00 | 0.25 | 0.64 | 0.39 | OK |
| career/application-tracker | 1.00 | 0.00 | 0.30 | 0.50 | 0.20 | OK |
| career/interview-prep | 1.00 | 0.00 | 0.12 | 0.34 | 0.22 | OK |
| career/jd-fit-scorer | 0.71 | 0.00 | 0.33 | 0.50 | 0.17 | BOTH |
| career/offer-evaluator | 1.00 | 0.00 | 0.19 | 0.62 | 0.44 | OK |
| career/outreach-and-followup | 1.00 | 0.00 | 0.31 | 0.53 | 0.22 | OK |
