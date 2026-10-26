# Estimate Memo — <Client> — <Initiative> — v0.1 (<yyyy-mm-dd>)

## Bottom line
| Item | Value | Basis |
|---|---|---|
| Effort quoted | <P80> person-days (P50 <n>, P90 <n>) | `scripts/estimate.py`, <n> iterations |
| Confidence level used | P80 / P90 / P50+NTE | <commercial model and reason> |
| Duration | <n> weeks from a stated staffing plan, else [TO BE BASELINED — owner: Estimation lead] | Critical path + staffing plan; `estimate.md` § Duration (the model computes effort only) |
| Team shape | <n> FTE peak; onshore/offshore <x/y> by phase | Staffing table |
| Price | <amount currency> or "pending rate card" | Rate card <name>, valid until <date> |
| Contingency | P80 − P50 = <n> person-days (<x>%) | Shown as a line |
| Basis mix | ANA <x>% · PAR <y>% · JUD <z>% | Flag if JUD > 30% |

## Basis of estimate
| Phase | Work packages | P50 (pd) | P80 (pd) | P90 (pd) | Share of variance |
|---|---|---|---|---|---|
| | | | | | |
| **Total** | | | | | |

## Assumptions
| ID | Assumption | Value | Source or `[TO BE BASELINED — owner: <role>]` | If false |
|---|---|---|---|---|
| A-01 | Interface count | | | Re-run model; price per unit × count |
| A-02 | Unit effort per complexity band | | | |
| A-03 | Client SME availability | | | |
| A-04 | Environments ready by | | | |
| A-05 | Rates valid until | | | |

## Exclusions
<licenses, cloud consumption, client effort, third-party fees, travel beyond <n> trips, data remediation…>

## Risks to the estimate and de-risking
| Risk | Effect on estimate | De-risk action | Owner |
|---|---|---|---|

## Sensitivity (top variance contributors)
| Task | P90 − P10 (pd) | Driver | De-risk |
|---|---|---|---|

## Staffing
| Role | Location | Phase 1 % | Phase 2 % | Phase 3 % | Total pd | Named? |
|---|---|---|---|---|---|---|

FTE by month:
| Month | 1 | 2 | 3 | 4 | 5 | 6 | … |
|---|---|---|---|---|---|---|---|
| FTE | | | | | | | |

Leverage ratio: <n>. Overlap hours with client: <n>/day (assumption A-nn).

## Price-to-win (if given)
| Item | Value |
|---|---|
| Our price at P80 | |
| Price-to-win | |
| Gap | |
| Levers (not estimate cuts) | scope phasing · mix shift · assets · client responsibilities · duration |
