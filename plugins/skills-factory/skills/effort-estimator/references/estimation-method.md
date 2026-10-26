# Estimation Method

## 1. WBS rules
| Rule | Practice |
|---|---|
| Hierarchy | Phase → work package → task. Three levels; a fourth only for programs > 5,000 person-days |
| Task size | 2–15 person-days. Larger tasks hide uncertainty; smaller tasks create false precision |
| Drivers | Prefer parametric tasks: `count × unit effort`. The count is an assumption; the unit effort is calibrated from actuals or the complexity scoring in `integration-migration-assessor` |
| Completeness | Mandatory packages: project management (8–15% of delivery effort), QA/test (20–35% for integration), environments and DevOps, data/test-data preparation, cutover and rehearsal, hypercare, knowledge transfer and documentation, governance and reporting. Add them explicitly even if "included" in rates elsewhere |
| Dependencies | Record predecessor task IDs; the critical path drives duration, not total effort |
| Exclusions | List what the WBS does not cover (licenses, client effort, third-party fees) |

## 2. Three-point calibration
| Point | Definition | Calibration guidance |
|---|---|---|
| Optimistic (O) | Everything goes right; experienced team; no rework | Rarely below 0.7× most likely |
| Most likely (M) | Normal conditions for this client; typical rework | Anchor on actuals when available |
| Pessimistic (P) | Known risks materialize (unclear requirements, access delays, defect-heavy legacy); not a disaster scenario | 1.5× M for well-understood work; 2–3× M for legacy migration, data-heavy, or first-of-a-kind tasks |

Basis codes: `ANA` analogy to a prior actual (cite the reference ID), `PAR` parametric (count × unit, cite the unit source), `JUD` expert judgment. Report the share of total M-effort by basis. If `JUD` > 30%, flag the estimate as low-confidence and recommend an assessment phase before fixed pricing.

Unit-effort anchors must come from the user's prior actuals or the assessor's complexity bands. Do not supply "industry" unit efforts; if none exist, mark `[TO BE BASELINED — owner: ___]` and run the model on judgment with the flag raised.

## 3. PERT and Monte Carlo
PERT mean per task: `(O + 4M + P) / 6`; standard deviation: `(P − O) / 6`.
Monte Carlo: sample each task from a Beta-PERT distribution (shape from O, M, P), sum per phase and total, repeat N ≥ 10,000 times. Report:
| Statistic | Use |
|---|---|
| P50 | Expected effort; T&M estimate |
| P80 | Fixed-price quote floor; contingency = P80 − P50 |
| P90 | Fixed-price for high-uncertainty migrations; board-level commitment |
| Phase P50/P80 | Milestone pricing |
| Variance contributors | Top tasks by variance; targets for de-risking (assessment, spike, prototype) |

Correlation: tasks sharing a driver (same count) move together. The script applies a shared multiplier per `driver_group` so that correlated uncertainty is not understated. Independent sampling of correlated tasks under-states P80.

## 4. Confidence selection
| Commercial model | Quote | Rationale |
|---|---|---|
| Fixed price, inventory known | P80 | Contingency covers normal variance |
| Fixed price, inventory unconfirmed | P90, or assessment first | Count uncertainty dominates |
| T&M | P50 estimate, P80 as NTE | Client holds risk; NTE protects budget |
| Assessment (fixed) | P80, short duration | Scope is bounded by time |
| Managed service transition | P80 | Transition risk is supplier's |

## 5. Duration
Duration ≠ effort ÷ team size. Compute from the critical path with realistic allocation (a 100%-allocated person yields ~80% productive days). Apply client-side constraints: freeze windows, SME availability, approval latency (assume 5 business days per gate unless the client states otherwise). Ramp-up: first two weeks of any new team member at 50%.

## 6. Sensitivity and de-risking
From the variance contributors, propose de-risking actions:
| Variance source | De-risk by |
|---|---|
| Unconfirmed counts | Inventory in an assessment phase; price per unit with a count band |
| Legacy complexity unknown | Spike on the 3 most complex items; re-score |
| Client dependency latency | Dependency register with dates; day-for-day clause in SOW |
| New technology for the team | Prototype in phase 0; training line in WBS |
| Data quality | Profiling task before build; data remediation as client responsibility or separate package |

## 7. Estimate memo structure
1. Bottom line: P80 effort (person-days), duration (weeks), team shape, price (if rate card) or "price pending rate card", confidence level used and why.
2. Basis of estimate: WBS summary table by phase (P50/P80), basis mix (ANA/PAR/JUD %).
3. Assumptions: counts, unit efforts, allocations, rates validity — each with source or `[TO BE BASELINED — owner: ___]`.
4. Exclusions.
5. Risks to the estimate and de-risking plan.
6. Sensitivity: top 5 variance contributors.
7. Staffing table (from `staffing-and-rates.md`).
8. Price-to-win comparison and levers (if a target was given).
