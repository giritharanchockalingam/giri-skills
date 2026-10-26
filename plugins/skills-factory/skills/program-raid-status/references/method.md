# Method

All thresholds below are this skill's own default convention, not an external standard. Override them per program with the `thresholds` input (layout: `assets/thresholds.csv`).

## Milestone RAG
| Condition (milestone not done) | RAG |
|---|---|
| forecast_date < as_of (date passed, not done) | red (`late`) |
| slip_days > amber_max_slip_days (default 10) | red |
| green_max_slip_days (default 0) < slip_days ≤ amber_max_slip_days | amber |
| slip_days ≤ green_max_slip_days | green |
| status `blocked` | at least amber |
| status `done` | complete (excluded from the overall RAG) |

slip_days = forecast_date − baseline_date in calendar days; a negative slip (ahead of plan) is green.

## Critical path
Critical-path method on a node-weighted DAG: each milestone's earliest finish = duration_days + the largest earliest finish among its `depends_on`. The path ending at the largest earliest finish, traced back through the predecessor with the largest earliest finish, is the critical path. Ties go to the lowest id so the displayed chain is deterministic. A backward pass then computes each milestone's float (latest finish − earliest finish against the project end); every zero-float milestone, including a parallel chain of equal length, is marked `on_critical_path = yes` and the tie is noted in the report (`critical_path_ties` in status.json). A cycle stops the run (exit 1) and names the milestones involved. No calendars or resource levelling.

raid-actions.csv may have zero data rows (a healthy program with no open RAID items); `--verify` accepts the header-only file and checks owner and next_action on every row that exists. Text cells in both CSVs that start with = + - @ tab or CR get a leading `'` (CSV-injection guard).

## RAID
- Exposure = likelihood × impact, each 1–5 (range 1–25). A risk must have both. An issue with a blank likelihood counts as 5 (it has already occurred). Other blanks leave exposure empty.
- overdue_days = max(0, as_of − due) for open items; age_days = as_of − raised (when `raised` is given).
- Overdue ageing buckets: 1–7, 8–30, 31+ days.
- A blank owner becomes `[TO BE BASELINED — owner: Program manager]`.
- next_action is built from rules: assign an owner, set a due date, re-plan an overdue item, validate an assumption, then the recorded mitigation (or "Define a mitigation").

## Overall RAG
1. RED if an open critical-path milestone is red, or an open RAID item with exposure ≥ red_exposure (default 20) is overdue.
2. AMBER if any open milestone is amber or red, any open RAID item is overdue, or any open item has no owner.
3. GREEN otherwise.

`--strict` exits 1 when the overall RAG is red; all outputs are still written.

## as_of
The status date is a required input. The skill never uses the system date.
