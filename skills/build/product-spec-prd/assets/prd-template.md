# PRD — {{TITLE}}

**{{Outcome sentence}}: target {{metric}} from {{baseline}} to {{target}} by {{date}}.**

| Field | Value |
|---|---|
| Status | Draft → In review → Approved → Shipped |
| Owner | [TO BE BASELINED — owner: ___] |
| Reviewers | |
| Related | SPEC §__ · PRD __ · ADR __ |
| Flag | `feature.<name>` |
| Target release | v__ |

## Exec summary (≤ 5 bullets)
- Problem: …
- Who: …
- What: …
- Success: …
- Scope: v1 = …; later = …

## Problem
| Evidence | Source | Date |
|---|---|---|
| | | |

What happens if we do nothing: …

## Users
| Persona | Role (RBAC) | Job to be done | Today's workaround |
|---|---|---|---|
| | | | |

## Goals
| # | Goal | Metric | Baseline | Target | Review date |
|---|---|---|---|---|---|
| G1 (primary) | | | | | |
| G2 (leading) | | | | | |
| Guardrail | | | | | |

## Non-goals (v1 will not …)
| Non-goal | Reason | Revisit in |
|---|---|---|
| | | |

## Metrics
| Metric | Baseline | Target | Source / instrumentation | Review date |
|---|---|---|---|---|
| | [TO BE BASELINED — owner: ___] | | | |

## Phases (scope by phase)
| Phase | Includes | Excludes | Exit criterion |
|---|---|---|---|
| v1 | | | |
| v1.1 | | | |
| Later | | | needs evidence: … |

## User stories and acceptance criteria (v1)
### S1 — As a <persona>, I want <capability> so that <outcome>
- Given … When … Then …
- Given a user without permission … When … Then "not allowed" and an audit entry
### S2 — …

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
- Acceptance criteria: S1.1, S1.2, S2.1 …
- Entities for supabase-schema-rls: …
- RBAC rows to add: …
- Metrics instrumentation: events `action=<…>` with `outcome`
- Flag: `feature.<name>`

## Appendix
Research, mockups, alternatives considered.
