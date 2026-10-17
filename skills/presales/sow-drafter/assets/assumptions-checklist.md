# Assumptions and Dependencies Checklist (Appendix C)

Walk every row. Each applicable item becomes an A-nn (assumption) or DEP-nn (dependency) in the SOW with basis, consequence, and owner. Mark N/A with a reason.

## Universal
| # | Item | A / DEP | Applies? | Basis / value | If false |
|---|---|---|---|---|---|
| U1 | Scope counts (interfaces, systems, users, sites, reports, courses, SKUs) as listed in Appendix A | A | | | Re-estimate; CR |
| U2 | Client provides environments (dev, test, UAT, perf, prod) by date | DEP | | | Day-for-day |
| U3 | Client provides access (VPN, repos, credentials, licenses) by date | DEP | | | Day-for-day |
| U4 | Named client SMEs available at stated allocation | DEP | | | Re-plan |
| U5 | Decisions returned within review windows | A | | | Deemed acceptance / shift |
| U6 | Third-party vendors cooperate (APIs, documentation, support) | A | | | CR |
| U7 | Freeze windows and blackout dates as listed | A | | | Re-plan |
| U8 | Working hours, time-zone overlap, holidays as stated | A | | | Re-plan |
| U9 | Documentation of current state exists and is accurate | A | | | Discovery effort CR |
| U10 | Security and compliance approvals (vendor onboarding, data access) granted by date | DEP | | | Day-for-day |
| U11 | Client-side tooling (ticketing, CI/CD, repos) available or supplier tooling accepted | A | | | CR |
| U12 | Data for testing (masked, representative) provided by date | DEP | | | Shift test phase |

## Integration / migration engagements
| # | Item | A / DEP | Applies? | Basis / value | If false |
|---|---|---|---|---|---|
| I1 | Interface inventory complete and scored; complexity distribution as per assessment | A | | | Re-estimate |
| I2 | Target platform licensed, provisioned, and accessible by date | DEP | | | Day-for-day |
| I3 | Legacy platform remains available for parallel run through date | DEP | | | Cutover risk; CR |
| I4 | Endpoint systems unchanged during migration (no concurrent upgrades) | A | | | CR |
| I5 | Existing test cases / data exist per interface; otherwise test creation in scope? | A | | | CR |
| I6 | Rollback approach agreed per wave | A | | | Cutover plan revision |
| I7 | Hypercare window and hours as stated | A | | | CR |

## Application build engagements
| # | Item | A / DEP | Applies? | Basis / value | If false |
|---|---|---|---|---|---|
| B1 | Requirements baselined and signed before build phase | DEP | | | Shift build |
| B2 | UX/design assets provided or in scope | A | | | CR |
| B3 | Identity provider and auth model decided | A | | | CR |
| B4 | Hosting/cloud account owned by client; consumption costs borne by client | A | | | Commercial CR |
| B5 | Accessibility and privacy standards named (WCAG level, regulations) | A | | | CR |
| B6 | Defect severity definitions and SLA for fix agreed | A | | | Acceptance disputes |

## Data / AI engagements
| # | Item | A / DEP | Applies? | Basis / value | If false |
|---|---|---|---|---|---|
| D1 | Data sources, volumes, and quality as assessed; access granted by date | DEP | | | Shift / CR |
| D2 | Model/LLM provider and usage costs borne by client; limits stated | A | | | Commercial CR |
| D3 | Evaluation set and acceptance thresholds agreed before build | DEP | | | Acceptance disputes |
| D4 | AI governance approvals (privacy, risk) obtained by date | DEP | | | Day-for-day |
| D5 | Human-in-the-loop roles staffed by client | DEP | | | Scope change |

## Managed service / run engagements
| # | Item | A / DEP | Applies? | Basis / value | If false |
|---|---|---|---|---|---|
| R1 | Baseline volumes (tickets, transactions, interfaces) as stated; bands defined | A | | | Band change CR |
| R2 | Transition period and knowledge-transfer sources available | DEP | | | Shift service start |
| R3 | Monitoring and tooling access granted | DEP | | | SLA suspension |
| R4 | Change volume limits per month | A | | | CR |
| R5 | Incumbent cooperation during transition | DEP | | | Shift / CR |

## Commercial
| # | Item | A / DEP | Applies? | Basis / value | If false |
|---|---|---|---|---|---|
| C1 | Rates valid until date; annual uplift rule | A | | | Reprice |
| C2 | Travel and expenses policy and cap | A | | | CR |
| C3 | Currency and tax treatment | A | | | Reprice |
| C4 | Payment terms per MSA | A | | | — |
