# PRD — Order CSV export

> Script draft — the model sharpen step was not run (draft only); every field comes from the brief.

**Order CSV export: Operations staff copy orders into spreadsheets by hand because the portal has no export. Target Operators using export per month from 0 (feature absent) to 60% of active operators by 2027-03-31.**

| Field | Value |
|---|---|
| Status | Draft → In review → Approved → Shipped |
| Owner | [TO BE BASELINED — owner: <role>] |
| Reviewers | |
| Related | SPEC §__ · PRD __ · ADR __ |
| Flag | `feature.exports` |
| Target release | v__ |

## Exec summary (≤ 5 bullets)
- Problem: Operations staff copy orders into spreadsheets by hand because the portal has no export
- Who: Operations lead, Finance analyst (viewer)
- What: Order CSV export
- Success: Operators using export per month → 60% of active operators
- Scope: v1 = CSV export of the current order list; Customer names quoted per RFC 4180; Download served by a route handler; later = Later

## Problem
| Evidence | Source | Date |
|---|---|---|
| [TO BE BASELINED — owner: Product owner] (no evidence supplied — assumption) | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] |

Problem statement: Operations staff copy orders into spreadsheets by hand because the portal has no export

What happens if we do nothing: [TO BE BASELINED — owner: Product owner]

Constraints: No schema change; Behind feature.exports flag

## Users
| Persona | Role (RBAC) | Job to be done | Today's workaround |
|---|---|---|---|
| Operations lead | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] |
| Finance analyst (viewer) | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] |

## Goals
| # | Goal | Metric | Baseline | Target | Review date |
|---|---|---|---|---|---|
| G1 (primary) | An operator exports the current order list as CSV in one click | Operators using export per month | 0 (feature absent) | 60% of active operators | [TO BE BASELINED — owner: Product owner] |
| G2 (leading) | Customer names with commas or quotes export intact | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] |
| Guardrail | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] |

## Non-goals (v1 will not …)
| Non-goal | Reason | Revisit in |
|---|---|---|
| Scheduled or emailed exports | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] |
| XLSX formatting | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] |
| Export of attachments | [TO BE BASELINED — owner: Product owner] | [TO BE BASELINED — owner: Product owner] |

## Metrics
| Metric | Baseline | Target | Source / instrumentation | Review date |
|---|---|---|---|---|
| Operators using export per month | 0 (feature absent) | 60% of active operators | logs action=orders.export outcome=ok | [TO BE BASELINED — owner: Product owner] |

## Phases (scope by phase)
| Phase | Includes | Excludes | Exit criterion |
|---|---|---|---|
| v1 | CSV export of the current order list; Customer names quoted per RFC 4180; Download served by a route handler | Scheduling; XLSX | 60% of active operators exported at least once in 30 days |
| Later | Scheduled exports to email | [TO BE BASELINED — owner: Product owner] | needs evidence: customer requests |

## User stories and acceptance criteria (v1)
### S1 — As Operations lead, I want: CSV export of the current order list
- Given the v1 build, When the user exercises "CSV export of the current order list", Then GET /api/orders/export answers 200 with text/csv and one row per order in the current list
- Verified by: unit toCsv returns the header plus one line per order and the route answers 200 text/csv
### S2 — As Operations lead, I want: Customer names quoted per RFC 4180
- Given the v1 build, When the user exercises "Customer names quoted per RFC 4180", Then a customer name holding a comma or a double quote exports as one quoted field with inner quotes doubled
- Verified by: unit toCsv quotes a name with a comma and doubles an inner quote
### S3 — As Operations lead, I want: Download served by a route handler
- Given the v1 build, When the user exercises "Download served by a route handler", Then the response carries a Content-Disposition attachment header naming orders.csv
- Verified by: route test asserts the Content-Disposition attachment header

## Experience notes
Entry points, empty states, error states, permission-denied state. Link to design if any.

## Data and tenancy
| Entity | New / changed | Tenant-scoped | Roles | Audited |
|---|---|---|---|---|
| | | | | |

## Dependencies
| Dependency | Owner | Needed by |
|---|---|---|
| | | |

## Risks
| Risk | L | I | Mitigation | Owner |
|---|---|---|---|---|
| | | | | |

## Open questions
| # | Question | Owner | Due | Default if unanswered |
|---|---|---|---|---|
| 1 | | | | |

## Rollout
Flag default off → internal tenants → 10% → 100%. Kill switch: flag off. Comms: …

## Engineering handoff (input to spec-to-plan)
- Acceptance criteria: GET /api/orders/export answers 200 with text/csv and one row per order in the current list; a customer name holding a comma or a double quote exports as one quoted field with inner quotes doubled; the response carries a Content-Disposition attachment header naming orders.csv
- Entities for supabase-schema-rls: [TO BE BASELINED — owner: Product owner]
- RBAC rows to add: [TO BE BASELINED — owner: Product owner]
- Metrics instrumentation: events `action=<…>` with `outcome` for Operators using export per month
- Flag: `feature.exports`

## Appendix
Research, mockups, alternatives considered.
