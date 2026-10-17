# Fix — {{TITLE}} — {{DATE}}

| Field | Value |
|---|---|
| Symptom | |
| Environment / version | prod / preview / local · sha |
| Evidence | error text · requestId · failing test |
| Root cause | `<file:line>` does X when Y because Z |
| Trigger (if different) | |

## Reproduction
`tests/…` or command — fails before fix: yes (seen red on `<sha>`)

## Change
| File | Lines | What |
|---|---|---|
| | | |

## Regression test
`tests/…` — `it('does not <bug> when <condition>')` — red before, green after (stash check done: yes)

## Verification
| Check | Command | Result |
|---|---|---|
| lint | `npm run lint` | |
| typecheck | `npm run typecheck` | |
| full unit | `npm test` | |
| integration / e2e | | |
| build | `npm run build` | |
| callers re-checked | `grep -rn "<fn>("` → N callers read | |

## Blast radius
Who else uses this path and why they are unaffected.

## Data impact
None / N rows affected → backfill migration `<name>` (reviewed, batched, idempotent)

## Rollback
redeploy `<previous tag>` / flag `<name>` off / revert migration `<name>`

## Parked (not done in this fix)
- …
