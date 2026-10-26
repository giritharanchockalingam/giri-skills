# Fairness metrics — definitions, worked example, choosing one

## Per-group rates (binary decision, positive = the outcome the decision grants or flags)
| Rate | Formula |
|---|---|
| Base rate | actual positives / n |
| Selection rate | predicted positives / n |
| Accuracy | (TP + TN) / n |
| TPR (recall) | TP / (TP + FN) — undefined when the group has no actual positives |
| FPR | FP / (FP + TN) — undefined when the group has no actual negatives |
| Precision | TP / (TP + FP) — undefined when the group has no predicted positives |

## Fairness metrics computed by `scripts/fairness.py`
| Metric | Formula | Better | Typical question |
|---|---|---|---|
| `demographic_parity_difference` | max − min selection rate | lower | Do groups receive the outcome at the same rate? |
| `disparate_impact_ratio` | min over groups of selection rate ÷ reference group's | higher | Does any group receive it at a fraction of the reference rate? |
| `equal_opportunity_difference` | max − min TPR | lower | Among those who qualify, are groups recognised equally? |
| `equalized_odds_difference` | max(TPR gap, FPR gap) | lower | Are both error types equal across groups? |

Gaps use every group with a defined rate (min-max across groups); per-group values versus the reference group are in the Per-group table. Undefined rates are excluded and named in the notes.

## Worked example (the eval fixture — fictional, hand-checked)
| Group | n | TP | FN | FP | TN | Selection | TPR | FPR |
|---|---|---|---|---|---|---|---|---|
| A (ref) | 10 | 4 | 1 | 1 | 4 | 5/10 = 0.5 | 4/5 = 0.8 | 1/5 = 0.2 |
| B | 10 | 2 | 2 | 1 | 5 | 3/10 = 0.3 | 2/4 = 0.5 | 1/6 ≈ 0.1667 |
| C | 3 | 1 | 0 | 0 | 2 | 1/3 ≈ 0.3333 | 1/1 = 1.0 | 0/2 = 0 |

DPD = 0.5 − 0.3 = 0.2 · DIR = min(0.3/0.5, 0.3333/0.5) = 0.6 · EOD = 1.0 − 0.5 = 0.5 · FPR gap = 0.2 − 0 = 0.2 · EqOdds = max(0.5, 0.2) = 0.5. With `min_sample` 5, group C (n = 3) is flagged: its TPR of 1.0 rests on one positive and drives the EOD.

## Choosing the governing metric (a policy decision — owner: Responsible AI lead)
- Outcome is a benefit allocated by rate (hiring shortlist, credit approval): selection-rate metrics (DPD, DIR) are the usual first screen.
- Errors carry the harm (fraud flags, clinical triage): error-rate metrics (equal opportunity, equalised odds).
- When base rates differ between groups, equal selection rates and equal error rates generally cannot both hold; pick deliberately and record why.
- The four-fifths rule (DIR ≥ 0.8) comes from the US Uniform Guidelines on Employee Selection Procedures; it is a screening heuristic in that context, not a universal standard. The skill applies it only when the user supplies 0.8.

## Standards (by name; read the source, the skill gives no legal opinion)
- NIST AI Risk Management Framework (AI RMF 1.0) — MEASURE function: fairness and bias evaluated and documented.
- NIST SP 1270, Towards a Standard for Identifying and Managing Bias in Artificial Intelligence.
- EU AI Act — data and data governance obligations for high-risk systems include examining possible biases.
- US Uniform Guidelines on Employee Selection Procedures (1978) — origin of the four-fifths rule.

## What this check does not do
- No confidence intervals or significance tests; small groups are flagged instead.
- No intersectional analysis unless the user encodes it in the attribute column (e.g. `F|45-54`).
- No label-bias detection; labels are treated as ground truth.
