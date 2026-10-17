# Behavioral eval scorecard
_provider=openai model=gpt-4.1-mini runs=1 seed=42 date=2026-10-17_
_estimated spend: $1.96_

| skill | trigger acc | FP rate | without | with | lift | verdict |
|---|---|---|---|---|---|---|
| presales/account-plan | 1.00 | 0.00 | 0.60 | 0.20 | -0.40 | BODY |
| presales/client-research-brief | 1.00 | 0.00 | 0.62 | 0.88 | 0.25 | OK |
| presales/competitive-positioning | 1.00 | 0.00 | 0.67 | 0.50 | -0.17 | BODY |
| presales/discovery-interview | 1.00 | 0.00 | 0.44 | 1.00 | 0.56 | OK |
| presales/effort-estimator | 0.50 | 0.00 | 0.10 | 0.00 | -0.10 | BOTH |
| presales/exec-deck-redline | 1.00 | 0.00 | 0.10 | 0.20 | 0.10 | BODY |
| presales/integration-migration-assessor | 0.50 | 0.00 | 0.43 | 0.57 | 0.14 | BOTH |
| presales/orals-prep | 0.50 | 0.00 | 0.14 | 0.57 | 0.43 | DESC |
| presales/proposal-writer | 1.00 | 0.00 | 0.29 | 0.71 | 0.43 | OK |
| presales/rfp-compliance-matrix | 1.00 | 0.00 | 0.00 | 0.10 | 0.10 | BODY |
| presales/solution-architecture-doc | 1.00 | 0.00 | 0.30 | 0.30 | 0.00 | BODY |
| presales/sow-drafter | 1.00 | 0.00 | 0.17 | 0.50 | 0.33 | OK |
| presales/value-case-builder | 1.00 | 0.00 | 0.36 | 0.09 | -0.27 | BODY |
