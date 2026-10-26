# Aging Rules

Age = days between `as_of` and `last_touch`. Applied to open rows only.

| Stage | WATCH at | STALE at | Auto-suggest at STALE |
|---|---|---|---|
| Identified | 3 days | 7 days | Apply or move to Passed |
| Applied | 7 | 14 | Escalation ladder touch 1–2; at 30 days move to Ghosted |
| Screen | 5 | 10 | Status check (light touch) |
| HM | 5 | 10 | Status check; ask for timeline |
| Panel | 5 | 10 | Status check (timeline variant) |
| Exec | 7 | 14 | Status check; note competing timelines |
| Offer | 2 | 5 | Respond or request extension |
| Stalled | 14 | 30 | Check in; at 60 days move to Ghosted |

## Status flags (computed, not stored)
| Flag | Condition |
|---|---|
| OK | age < WATCH and next_action_date ≥ as_of |
| DUE | next_action_date ≤ as_of |
| WATCH | WATCH ≤ age < STALE |
| STALE | age ≥ STALE |
| OVERDUE | next_action_date < as_of − 3 days |
| MISSING | open row with empty next_action or next_action_date |

A row can carry two flags (e.g., STALE + OVERDUE). Report the most severe first: MISSING > OVERDUE > STALE > DUE > WATCH > OK.

## Review order
1. MISSING — fix data first.
2. OVERDUE and DUE — do today.
3. STALE — pick a touch from `outreach-and-followup` cadence or close the row.
4. WATCH — note only.

## Ghosting rule
Applied ≥ 30 days or Stalled ≥ 60 days with no company-initiated contact → Ghosted, `close_reason: "No response after N days"`. The user confirms before closure.
