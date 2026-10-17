# Security Review — {{SCOPE}} — {{DATE}}

| Field | Value |
|---|---|
| Scope | PR #__ / tag __ / files __ |
| Reviewer | |
| Trust model | roles: __ ; tenancy: __ ; public surfaces: __ |
| Verdict | BLOCK / MERGE WITH FIXES / MERGE |

## Findings (worst first)
| # | Sev | Confidence | Title | Trace (entry → sink) | Impact | Fix | Test | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | High | confirmed | | `a.ts:12 → b.ts:40 → table` | | | `tests/…` | fixed / open (owner, date) |

## Threat model record
| Change | Who reaches | Controls | Touches | Worst outcome | Control in diff? | Detection |
|---|---|---|---|---|---|---|
| | | | | | yes / no → finding # | |

## Surfaces reviewed
| Surface | Files | Notes |
|---|---|---|
| Server actions | | |
| Route handlers | | |
| Migrations / policies | | |
| Client components | | |
| Env / CI | | |
| External calls | | |

## Verification
| Check | Result |
|---|---|
| `rls_lint.py` | |
| lint / typecheck / unit | |
| Regression tests for Critical/High | |
| Re-trace after fix | |

## Out of scope / parked
- …
