# Plan — order-csv-export — 2026-10-22

<!-- FICTIONAL fixture: the architect's refined plan for the delivery-pipeline tests (Harborline Portal is invented) -->

| Field | Value |
|---|---|
| Source | SPEC §Order CSV export |
| Status | Draft → Approved → In progress → Done |
| Approved by / on | pending plan-approval |
| Size | MMM (3 tasks) |
| Flag | `feature.exports` |

## Outcome (one sentence)
Operators export the current order list as a CSV download so that nobody copies orders into spreadsheets by hand.

## Decisions (from brainstorm)
| Question | Answer | Source |
|---|---|---|
| Where does the CSV serialisation live? | lib/orders.js (toCsv), next to the order list it serialises | user |
| How is the file served? | a route handler at app/api/orders/export | brief |

## File table (read before listing)
| Path | Action | Why | Risk |
|---|---|---|---|
| lib/orders.js | modify | add toCsv with RFC 4180 quoting | none |
| app/api/orders/export/route.js | create | GET handler that streams the CSV as an attachment | auth |

## Tasks (execute in order; each gated)
### T1 — CSV export of the current order list (M)
- Files: lib/orders.js,app/api/orders/export/route.js
- Acceptance: GET /api/orders/export answers 200 with text/csv and one row per order in the current list
- Tests: unit toCsv returns the header plus one line per order and the route answers 200 text/csv
- Rollback: remove the route handler and the toCsv export from lib/orders.js
- Status: ☐ built ☐ tests pass ☐ full suite pass

### T2 — Customer names quoted per RFC 4180 (M)
- Files: lib/orders.js
- Acceptance: a customer name holding a comma or a double quote exports as one quoted field with inner quotes doubled
- Tests: unit toCsv quotes a name with a comma and doubles an inner quote
- Rollback: revert the quoting change in lib/orders.js
- Status: ☐ built ☐ tests pass ☐ full suite pass

### T3 — Download served by a route handler (M)
- Files: app/api/orders/export/route.js
- Acceptance: the response carries a Content-Disposition attachment header naming orders.csv
- Tests: route test asserts the Content-Disposition attachment header
- Rollback: remove app/api/orders/export/route.js
- Status: ☐ built ☐ tests pass ☐ full suite pass

## Repo check

Files looked up in `repo`:

- T1: lib/orders.js: modify; app/api/orders/export/route.js: create
- T2: lib/orders.js: modify
- T3: app/api/orders/export/route.js: create

No problems found.

## Gates
| Gate | Entry | Exit evidence |
|---|---|---|
| plan | spec section + repo read | this file: file table, tasks, risks, rollback |
| approve | plan posted | explicit "go" from the user |
| build | task N started | diff limited to task N's file list |
| test | task N code done | task N tests pass AND full unit suite passes |
| verify | all tasks done | lint + typecheck + unit + build green; e2e on touched paths; criteria ticked |

A gate without its exit evidence is not passed. Order: plan → approve → build → test → verify.

## Risks
| Risk | L | I | Mitigation | Owner |
|---|---|---|---|---|
| A name with embedded newlines breaks a row | L | M | quote every field that holds a comma, quote or newline | Tech lead |

## Rollback (whole feature)
- T1: remove the route handler and the toCsv export from lib/orders.js
- T2: revert the quoting change in lib/orders.js
- T3: remove app/api/orders/export/route.js
- Whole feature: turn the feature.exports flag off; no migration to reverse

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
- Scheduled or emailed exports; XLSX formatting
