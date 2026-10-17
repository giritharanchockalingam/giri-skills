# Token-Efficiency Rules (applies to every build/engineering skill)

Token usage on these projects is heavy. Work effectively and efficiently. Never break one thing while fixing another.

| # | Rule | Practice |
|---|---|---|
| 1 | Plan, then build | Write the plan (files to touch, tests to add, acceptance criteria) before code. Get a "go" on expensive or ambiguous work. |
| 2 | Fix, don't redo | Minimal diff. Edit the failing lines; never regenerate a file to change three lines. |
| 3 | Batch related asks | Group related changes into one pass; don't make 5 round-trips for one feature. |
| 4 | Push only changed files | Commits and uploads contain only what changed. No whole-tree rewrites. |
| 5 | Recurring context lives in repo docs | `SPEC.md` (what), `CLAUDE.md` (how we work here), `HANDOFF.md` (where we are). Never re-explain in chat what the repo already says. |
| 6 | Automate repeated workflows | If a sequence runs twice, it becomes a script, a Make target, or a skill. |
| 7 | One topic per thread | New topic → new thread, started from `HANDOFF.md`. |
| 8 | Fix in code, not in data | Handle the scenario in code so it is handled going forward. No SQL patches or hand-edited rows as a "fix". |
| 9 | Verify before claiming done | Run the test/build/lint. "Should work" is not done. |
| 10 | Read before writing | Read the file before editing it. Never assume contents from memory. |

## HANDOFF.md contract
```
# HANDOFF — <project> — <date>
## State: <one line>
## Done this thread
- …
## Changed files
- path — why
## Open items (owner)
- …
## Next thread starts with
<the exact prompt to paste>
```
