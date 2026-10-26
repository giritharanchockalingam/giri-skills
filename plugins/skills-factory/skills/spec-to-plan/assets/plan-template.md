# Plan — {{SLUG}} — {{DATE}}

| Field | Value |
|---|---|
| Source | SPEC §__ / ticket __ |
| Status | Draft → Approved → In progress → Done |
| Approved by / on | |
| Size | S / M / L (sum of tasks) |
| Flag | `feature.<name>` or none |

## Outcome (one sentence)
Users can … so that …

## Decisions (from brainstorm)
| Question | Answer | Source |
|---|---|---|
| | | user / default |

## File table (read before listing)
| Path | Action | Why | Risk |
|---|---|---|---|
| | create / modify | | schema / auth / none |

## Tasks (execute in order; each gated)
### T1 — <name> (S)
- Files: …
- Acceptance: Given … When … Then …
- Tests: unit `tests/unit/…`; integration …; e2e …
- Rollback: …
- Status: ☐ built ☐ tests pass ☐ full suite pass

### T2 — …

## Risks
| Risk | L | I | Mitigation | Owner |
|---|---|---|---|---|
| | | | | |

## Rollback (whole feature)
…

## Verification record (filled at the end)
| Check | Command | Result |
|---|---|---|
| lint | `npm run lint` | |
| typecheck | `npm run typecheck` | |
| unit + coverage | `npm test -- --coverage` | |
| build | `npm run build` | |
| e2e | `npm run test:e2e -- <spec>` | |
| rls lint | `python3 -I scripts/rls_lint.py supabase/migrations` | |

## Out of scope / parked
- …
