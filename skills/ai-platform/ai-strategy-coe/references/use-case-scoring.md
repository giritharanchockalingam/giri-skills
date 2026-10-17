# Use-Case Scoring Rubric — value × feasibility × data readiness ÷ risk

Score 1–5 on each axis. Score with evidence; mark unknowns. Record scores in `assets/use-case-scoring.csv`.

## Axes
### Value (V)
| Score | Criteria |
|---|---|
| 1 | No quantified benefit; "nice to have" |
| 2 | Qualitative benefit; small user group |
| 3 | Quantified benefit with a baseline; single function; owner named |
| 4 | Quantified benefit material to a function's plan; multiple teams; revenue or cost line identified |
| 5 | Enterprise-level benefit tied to a strategic priority; sponsor at executive level; benefit baselined in finance |

### Feasibility (F)
| Score | Criteria |
|---|---|
| 1 | Research-grade problem; no known pattern; unclear success definition |
| 2 | Known pattern but major integration or process change required; success definition fuzzy |
| 3 | Known pattern (RAG, classification, extraction, summarization, agentic workflow with bounded tools); integration points exist; success measurable |
| 4 | Pattern proven elsewhere in the organization; APIs and data accessible; team available |
| 5 | Near-configuration; vendor or platform feature; weeks not months |

### Data readiness (D)
| Score | Criteria |
|---|---|
| 1 | Data does not exist or is not captured |
| 2 | Exists, but unstructured, unowned, or not accessible without legal review |
| 3 | Accessible with an owner; quality unknown or partly documented |
| 4 | Curated, documented, access via role; sufficient volume and freshness |
| 5 | Data product with SLA; already used by another production system |

### Risk (R) — higher is riskier
| Score | Criteria |
|---|---|
| 1 | Internal, low-stakes, human reviews every output |
| 2 | Internal, decision support, reversible outcomes |
| 3 | Customer-facing or employee-impacting, with human in the loop; moderate privacy exposure |
| 4 | Autonomous actions on customer/employee data; regulated domain (credit, employment, health, education records); IP exposure |
| 5 | Safety, legal, or regulatory outcome without reliable human oversight; likely "high-risk" under EU AI Act or equivalent |

## Formula
```
priority = (V × F × D) / R
```
Range: 0.2 (1×1×1/5) to 125 (5×5×5/1). Rank descending. Do not weight axes unless the sponsor states a weighting; if they do, record it.

## Classification
| Band | Rule | Action |
|---|---|---|
| Now | Top quartile by priority AND R ≤ 3 AND D ≥ 3 | Fund in Q1–Q2; lighthouse candidates |
| Next | Second quartile, or top quartile blocked by D ≤ 2 | Fund data readiness work first |
| Later | Third quartile | Revisit at next portfolio review |
| Stop | V ≤ 2, or R = 5 with no mitigation path, or F = 1 | Close with a one-line reason |

## Rules
1. Score at least 8 candidates before ranking; fewer means the backlog is not elicited yet.
2. Every "Now" case names a business owner and a measurable baseline. No owner → demote to Next.
3. Keep one "boring" high-D, high-F case in Now (document extraction, ticket triage) to prove the platform while a lighthouse matures.
4. Re-score quarterly; publish deltas.
5. Portfolio balance target (assumption, state it): 60% productivity/cost, 30% revenue/experience, 10% exploratory.
