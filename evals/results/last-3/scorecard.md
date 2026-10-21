# Behavioral eval scorecard
_provider=openai model=gpt-4.1-mini runs=2 seed=42 date=2026-10-21_
_estimated spend: $1.91_

| skill | trigger acc | FP rate | without | with | lift | verdict |
|---|---|---|---|---|---|---|
| ai-platform/ai-vendor-assessment | 0.86 | 0.00 | 0.44 | 0.83 | 0.39 | OK |
| ai-platform/data-readiness-assessment | 1.00 | 0.00 | 0.50 | 0.83 | 0.33 | OK |
| ai-platform/program-raid-status | 1.00 | 0.00 | 0.50 | 0.55 | 0.05 | BODY |
