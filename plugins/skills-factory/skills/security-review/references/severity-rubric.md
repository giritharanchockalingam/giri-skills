# Severity Rubric

Severity = reachability × impact, judged for this application, not the category's reputation.

## Reachability
| Level | Who can trigger |
|---|---|
| R3 | Unauthenticated internet |
| R2 | Any authenticated user (any tenant) |
| R1 | Privileged user (tenant admin/owner) or requires another vuln |
| R0 | Internal only (CI, operators) |

## Impact
| Level | Outcome |
|---|---|
| I3 | Cross-tenant data read/write, auth bypass, RCE, secret exposure, money movement |
| I2 | Own-tenant privilege escalation, bulk PII of own tenant, data integrity loss, persistent DoS |
| I1 | Limited info leak (existence, counts), single-record integrity, temporary DoS |
| I0 | Hardening, defence in depth, hygiene |

## Matrix
| | I3 | I2 | I1 | I0 |
|---|---|---|---|---|
| R3 | Critical | High | Medium | Low |
| R2 | Critical | High | Medium | Low |
| R1 | High | Medium | Low | Info |
| R0 | Medium | Low | Info | Info |

## Handling
| Severity | Action | SLA |
|---|---|---|
| Critical | Block merge/release; fix now; regression test; notify owner | same day |
| High | Block merge; fix in this PR; regression test | before merge |
| Medium | Fix in this PR if ≤1 h, else ticket with owner + date | ≤ 2 weeks |
| Low | Ticket or fix opportunistically | next cycle |
| Info | Note in report | — |

## Confidence
Attach `confirmed` (exploit sketch works by trace), `likely` (trace complete, exploit untested), or `question` (gap suspected, needs author input). Only `confirmed`/`likely` carry severity.
