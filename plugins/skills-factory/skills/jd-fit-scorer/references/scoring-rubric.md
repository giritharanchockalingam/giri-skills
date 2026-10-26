# Scoring Rubric

## Weights
| Bucket | Weight | What goes in it |
|---|---|---|
| Must-haves | 60 | "Required", "must", minimum years, degree, certification, clearance, named platforms listed as required |
| Nice-to-haves | 25 | "Preferred", "plus", "ideally", "bonus", industry familiarity, secondary tools |
| Culture / logistics | 15 | Location, remote/hybrid policy, travel %, reporting line, team size, budget ownership, comp band, industry alignment with user's priorities |
| Red flags | subtract | Penalties from `red-flag-catalog.md`; applied after bucket scores |

## Item status values
| Status | Credit | Rule |
|---|---|---|
| MATCH | 1.0 | Profile line states the skill/outcome directly, within the last 7 years |
| PARTIAL | 0.5 | Adjacent skill (e.g., MuleSoft when JD says Boomi), or direct match older than 7 years, or scope one level smaller than asked |
| GAP | 0.0 | No profile evidence. Title inference does not count |

## Bucket math
```
bucket_score = weight × (Σ credit / item_count)
total = must + nice + culture − Σ red_flag_penalties
clamp to 0..100
```
If a bucket has zero items, redistribute its weight proportionally to the others and say so.

## Level calibration (Sr Director / VP / exec IT)
| Dimension | Expect in a Sr Director JD | Treat as PARTIAL if profile shows |
|---|---|---|
| Org scope | 30–150 people, multiple teams/vendors | <15 people or dotted-line only |
| Budget | $5M–$50M run + change | No stated budget ownership |
| Stakeholders | VP/C-level, board exposure optional | Director-level only |
| Transformation | Multi-year program, platform migration, M&A | Single-project delivery |
| P&L | Cost-center accountable; VP roles may want P&L | Project budgets only |

## Culture/logistics sub-scoring
| Item | MATCH | PARTIAL | GAP |
|---|---|---|---|
| Location | In user's allowed list or remote | Relocation offered, city acceptable | Onsite in excluded city |
| Travel | ≤ user's stated max | ≤ max + 10 pts | Above that |
| Reporting line | Reports to CIO/CTO/SVP | Reports to Director | Reports below Director (title inflation) |
| Comp band | Listed and ≥ floor | Not listed | Listed and below floor (hard constraint) |
