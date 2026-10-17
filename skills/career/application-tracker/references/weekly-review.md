# Weekly Review Ritual (30 minutes, same day each week)

## Steps
| # | Step | Tool | Output |
|---|---|---|---|
| 1 | Run aging as of today | `tracker.py aging` | Flagged rows |
| 2 | Fix MISSING rows | `tracker.py update` | Every open row has next action + date |
| 3 | Clear OVERDUE / DUE | `outreach-and-followup` | Touches sent, rows updated |
| 4 | Decide on STALE | user | Touch, close, or wait (with reason) |
| 5 | Count the funnel | `tracker.py list` | Table below |
| 6 | Top up the pipeline | `jd-fit-scorer` | Target: ≥ N new Identified rows per week (user sets N) |
| 7 | One decision | user | What to add, drop, or change in approach |

## Review output format
```
# Weekly review — <date>

## Funnel
| Stage | Open | Added this week | Closed this week |
| Identified | | | |
| Applied | | | |
| Screen | | | |
| HM | | | |
| Panel | | | |
| Exec | | | |
| Offer | | | |

## Flags
| ID | Company | Role | Stage | Age | Flag | Action | Due |

## Actions due this week
| Due | ID | Company | Action | Owner |

## Conversion (rolling 8 weeks)
| Applied → Screen | Screen → HM | HM → Panel | Panel → Exec | Exec → Offer |
| x% | | | | |

## Decision this week
One sentence: what changes.

## Parked
Items noticed but out of scope this week.
```

## Health thresholds (user may override)
| Signal | Healthy | Warning |
|---|---|---|
| Open active rows (Applied–Exec) | 8–15 | < 5 or > 25 |
| Applied → Screen conversion | ≥ 20% | < 10% → revisit targeting / résumé |
| Screen → HM | ≥ 50% | < 30% → revisit screen answers |
| Panel/Exec → Offer | ≥ 30% | < 15% → revisit interview-prep |
| Referral share of applications | ≥ 40% | < 20% → more outreach |
