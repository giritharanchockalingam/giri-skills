# Pipeline Stages

| Order | Stage | Enter when | Typical next action | Exit to |
|---|---|---|---|---|
| 0 | Identified | JD found, fit score pending or ≥ LEAN GO | Score JD; find referral | Applied / Passed |
| 1 | Applied | Application submitted | Follow up day 7 | Screen / Ghosted / Rejected |
| 2 | Screen | Recruiter or HR screen scheduled or done | Prep for HM; send availability | HM / Rejected |
| 3 | HM | Hiring-manager interview scheduled or done | Thank-you; prep panel | Panel / Rejected |
| 4 | Panel | Panel / peer / team round | Thank-yous; prep exec round | Exec / Rejected |
| 5 | Exec | CIO / CEO / board-style round | Thank-you; references ready | Offer / Rejected |
| 6 | Offer | Written or verbal offer received | Run offer-evaluator; negotiate | Accepted / Declined |
| 7 | Accepted | Signed | Notice, start date tasks | — (closed) |
| 8 | Declined | User declined | Door-open note | — (closed) |
| 9 | Rejected | Company declined | Ask for feedback once; 90-day touch | — (closed) |
| 10 | Passed | User chose not to apply | Record reason | — (closed) |
| 11 | Ghosted | No response past aging threshold | 90-day touch | — (closed) |
| 12 | Stalled | Process paused by company (freeze, reorg) | Check in per cadence | Any active stage / Ghosted |

Open stages: 0–6, 12. Closed stages: 7–11.

## Transition rules
- Stages may be skipped forward (e.g., Applied → HM via referral) but not backward except to Stalled.
- Every transition sets `last_touch` to the event date and requires a new `next_action` + `next_action_date` unless the row closes.
- Closing a row requires `close_reason` (one line).

## Word mapping
| User says | Stage |
|---|---|
| "submitted", "applied", "sent it in" | Applied |
| "recruiter call", "HR screen", "phone screen" | Screen |
| "hiring manager", "HM round", "met the director" | HM |
| "loop", "panel", "team interview", "peers" | Panel |
| "CIO round", "final", "CEO", "case presentation" | Exec |
| "verbal offer", "offer letter" | Offer |
| "no", "not moving forward", "TBNT" | Rejected |
| "no reply", "silence" | Ghosted (if threshold met) else current stage with flag |
