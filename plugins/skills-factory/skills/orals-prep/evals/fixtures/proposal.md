# Northwind Retail — Order Hub Integration — Proposal

## 1. Executive summary
**Northwind Retail will cut split shipments from 6.2% to 3% by wave 3.**

## 6. Scope and deliverables
| ID | Deliverable | Description | Acceptance criteria | Phase | Format |
|---|---|---|---|---|---|
| D-01 | Interface inventory and complexity scores | 118 interfaces scored Simple/Medium/Complex | Client VP Apps signs the scored inventory; 100% of interfaces banded | Wave 0 | CSV + memo |
| D-02 | Wave 1 migration (40 simple interfaces) | Rebuilt on target platform with parallel run | Parallel-run variance ≤ 0.5% over 10 business days | Wave 1 | Deployed interfaces + test evidence |
| D-03 | Cutover runbook | Step list with rollback | | Wave 1 | Markdown |

Out of scope (explicit): ERP upgrade; store POS replacement; data warehouse changes.
Client responsibilities: inventory export by 2026-09-15; test data per wave.

## 7. Timeline
| Milestone | Date / week | Depends on (client) | Freeze / blackout respected |
|---|---|---|---|
| Wave 0 complete | week 6 | inventory export | yes |
| Wave 1 cutover | week 16 | test data | peak freeze 2026-11-10 |

## 8. Team and governance
| Role | Responsibility | Allocation (%) | Location | Named (if confirmed) |
|---|---|---|---|---|
| Engagement manager | Delivery, governance | 50 | onshore | |
| Integration lead | Design, wave planning | 100 | onshore | |

## 9. Risks and assumptions
Assumption register:
| ID | Assumption | Basis | If false → | Change control (Y/N) | Confirm by |
|---|---|---|---|---|---|
| A-01 | 118 interfaces in scope per inventory export | client inventory 2026-09-15 | effort scales per unit | Y | VP Apps |
| A-02 | No cutover inside the peak freeze 2026-11-10 to 2027-01-05 | CTO statement | wave 2 shifts | Y | CTO |

## 10. Pricing
| Component | Basis (fixed / T&M / run-rate) | Amount | Notes |
|---|---|---|---|
| Wave 0 | fixed | USD 180,000 | |
