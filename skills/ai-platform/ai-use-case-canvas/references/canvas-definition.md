# One-Page AI Use-Case Canvas — definition

Nine boxes. Each box has a prompt question and a quality test. A box that cannot be filled after one round of questions is a finding in itself.

| # | Box | Prompt | Quality test |
|---|---|---|---|
| 1 | Problem and user | Who does what today, and what goes wrong (time, errors, cost, experience)? | A named role and a measurable pain; not "improve efficiency" |
| 2 | Decision or task affected | What decision or output changes because of the AI? Who acts on it? | One decision; the actor is a person or a system with a named owner |
| 3 | Current process and baseline | Steps, volume per period, time per unit, error/rework rate, cost | At least one number with a source, or `[TO BE BASELINED — owner: ___]` |
| 4 | Proposed AI capability | Pattern (extract / classify / summarize / retrieve-and-answer / generate / agentic workflow) and the boundary of autonomy | Pattern named; autonomy stated (suggest / draft / act with approval / act) |
| 5 | Data | Sources, owner, access path, volume, quality signal, sensitivity (PII, regulated), freshness | Owner and access path named; sensitivity classified |
| 6 | Feasibility | Known pattern? Integration points exist? Team available? Evaluation definable? | Each question answered yes/no with a note |
| 7 | Value hypothesis | Benefit type (cost, revenue, risk, experience), mechanism, estimate with assumptions, who signs the baseline | Mechanism explicit ("reduces handling time per ticket by X → Y FTE-hours/month"); estimate labeled assumption |
| 8 | Risks and tier | Top 3 risks (bias, privacy, hallucination, security, misuse, operational), internal tier (low/medium/high) | Tier justified by criteria; mitigations named at headline level |
| 9 | Build / buy / partner and next step | Decision with two strongest factors; the single 30-day step with owner | Step is concrete (e.g., "pull 200 historical cases and label 50 with SME by <date>") |

## Scores (from ai-strategy-coe rubric)
| Axis | Score 1–5 | Evidence |
|---|---|---|
| Value (V) | | |
| Feasibility (F) | | |
| Data readiness (D) | | |
| Risk (R; higher = riskier) | | |
| Priority = V×F×D÷R | | |

## Verdict rules
| Verdict | Condition |
|---|---|
| Proceed to design | V ≥ 3, F ≥ 3, D ≥ 3, R ≤ 3, owner and baseline named |
| Proceed after data readiness | V ≥ 3, F ≥ 3, D ≤ 2 — next step is a data task |
| Park | V ≤ 2 or F ≤ 2 now, with a revisit trigger |
| Stop | R = 5 without mitigation path, or no identifiable user/decision |

## Common disqualifiers found at this stage
- The "AI" is a lookup or rule that code can do deterministically → build the rule.
- No one owns the baseline → cannot prove value; park until an owner exists.
- Data is in people's heads or email only → data readiness project first.
- Output is a regulated decision with no human oversight planned → re-scope to "suggest" or stop.
