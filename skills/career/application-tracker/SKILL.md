---
name: application-tracker
description: Use when the user reports any application event (applied, recruiter screen booked, interview done, offer, rejection, ghosted) or asks for their pipeline, what is stale, or a weekly job-search review. Maintains tracker.csv (one row per opportunity) with stage, next action and dates; produces a pipeline table, an aging/stale list, and a weekly review summary. Includes a stdlib CLI (tracker.py) for add/update/list/aging.
license: MIT
metadata:
  domain: career
  adlc_stage: career
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: tracker, type: csv, required: true, copy: true, from: "tracker CSV (layout: assets/tracker.csv); a copy in {out} is updated, the original is untouched"}
      - {name: action, type: string, required: false, from: "add | update (applied to the copy before the reports)"}
      - {name: args, type: args, required: false, from: "arguments for the action, e.g. \"--company X --role Y --stage Applied --date 2026-10-01\""}
      - {name: as_of, type: string, required: false, from: "YYYY-MM-DD for the aging report (default today)"}
    run:
      - {step: event, kind: script, cmd: "python3 -I scripts/tracker.py {action} --file {tracker} {args}", stdout: "{out}/event.txt", skip_if_missing: [action]}
      - {step: pipeline, kind: script, cmd: "python3 -I scripts/tracker.py list --file {tracker} --json", stdout: "{out}/pipeline.json"}
      - {step: aging, kind: script, cmd: "python3 -I scripts/tracker.py aging --file {tracker} --json [--as-of {as_of}]", stdout: "{out}/aging.json"}
      - {step: weekly, kind: script, cmd: "python3 -I scripts/tracker.py aging --file {tracker} [--as-of {as_of}]", stdout: "{out}/weekly-review.md"}
    outputs:
      - {path: "{out}/tracker.csv", checks: [exists, csv:[id,company,role,stage,applied_date,last_touch,next_action,next_action_date]]}
      - {path: "{out}/pipeline.json", checks: [exists, json]}
      - {path: "{out}/aging.json", checks: [exists, json]}
      - {path: "{out}/weekly-review.md", checks: [exists]}
    modes:
      new: {case: agent-mode-new, bring: "an empty tracker and your first application"}
      existing: {case: agent-report-only, bring: "your current tracker spreadsheet"}
---

# Application Tracker

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py career/application-tracker --input <name>=<value> … --out <dir>` (see `--explain career/application-tracker`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

## Starting points
- **New** — start from the empty tracker layout: your first application is logged and the pipeline and aging reports begin.
- **Existing** — your current tracker is read (a copy is updated, the original is untouched): the pipeline, the aging report and the weekly review flag what is stale, overdue or missing a next action.

## When to use
- "Log that I applied to X", "move Y to panel stage", "what's stale?", "run my weekly review", "show the pipeline".
- After any `outreach-and-followup` touch or `interview-prep` session.
- NOT for: scoring a JD (`jd-fit-scorer`), comparing offers (`offer-evaluator`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| tracker.csv (existing) | yes | user file; create from `assets/tracker.csv` if none |
| Event details: company, role, stage, date, next action, next action date | yes | user |
| Source (referral, recruiter, board), fit score, comp band | no | user / `jd-fit-scorer` output |

Missing stage or date: ask once. Default the date to today only if the user says "today".

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md`.
2. Load `references/pipeline-stages.md`; map the user's words to a canonical stage. Reject unknown stages.
3. Apply the change with `scripts/tracker.py` (preferred) or edit the CSV directly, preserving the header and column order in `assets/tracker.csv`.
   - `python3 scripts/tracker.py add --file tracker.csv --company "X" --role "Y" --stage Applied --date 2026-10-16 --next "Follow up with recruiter" --next-date 2026-10-23`
   - `python3 scripts/tracker.py update --file tracker.csv --id 7 --stage "Panel" --date 2026-10-20 --next "Send thank-yous" --next-date 2026-10-21`
   - `python3 scripts/tracker.py list --file tracker.csv [--stage Applied] [--open]`
   - `python3 scripts/tracker.py aging --file tracker.csv [--as-of 2026-10-16]`
4. For a weekly review, run `aging` and follow `references/weekly-review.md`: pipeline by stage, stale items with the rule that fired, actions due this week, funnel counts, one decision (what to add, what to drop).
5. Every stale row gets a next action that the user confirms; no silent reassignment.
6. Run the self-check. Reply ≤50 words; tables are the artifact.

## Output
- Updated `tracker.csv` (same path the user supplied).
- Pipeline table: `| ID | Company | Role | Stage | Last touch | Next action | Due | Age (days) | Status |`
- Weekly review (Markdown) per `references/weekly-review.md`.

## Self-check
- [ ] Every row has a canonical stage, a last-touch date, and a next action with a date (closed rows excepted)
- [ ] Aging rules from `references/aging-rules.md` applied as-of the stated date
- [ ] No row added or changed beyond what the user reported
- [ ] CSV header unchanged; dates ISO `YYYY-MM-DD`
- [ ] Weekly review ends with one decision and the actions due this week

## References
- `references/pipeline-stages.md` — canonical stages and transitions
- `references/aging-rules.md` — stale thresholds per stage, status flags
- `references/weekly-review.md` — review ritual and output format
- `assets/tracker.csv` — header + EXAMPLE row
- `scripts/tracker.py` — CLI (stdlib)
