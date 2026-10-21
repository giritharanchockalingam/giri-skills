# Behavioral eval scorecard
_provider=openai model=gpt-4.1-mini runs=2 seed=42 date=2026-10-21_
_estimated spend: $2.47_

| skill | trigger acc | FP rate | without | with | lift | verdict |
|---|---|---|---|---|---|---|
| presales/account-plan | 1.00 | 0.00 | 0.32 | 0.82 | 0.50 | OK |
| presales/client-research-brief | 1.00 | 0.00 | 0.33 | 0.55 | 0.23 | OK |
| build/security-review | 1.00 | 0.00 | 0.31 | 0.50 | 0.19 | BODY |
| career/jd-fit-scorer | 1.00 | 0.00 | 0.33 | 0.47 | 0.13 | BODY |
