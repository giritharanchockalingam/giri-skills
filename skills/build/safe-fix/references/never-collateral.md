# Never-Collateral Rules

Adopted from the token-efficiency rules (fix-don't-redo, verify-before-done, fix-in-code) and Karpathy-style guardrails (no assumptions, minimal diffs, verify before claiming).

| # | Rule | Violation looks like | Instead |
|---|---|---|---|
| 1 | No fix without a reproduction | "I think this is it, try now" | failing test or command first |
| 2 | Read before writing | editing a file from memory of its contents | open it; read callers |
| 3 | One root cause, one diff | fixing three "suspicious" things at once | confirm the cause; change that one thing |
| 4 | Touch only the failing path | reformatting, renaming, moving code, upgrading deps in the fix PR | separate PR with suite green between |
| 5 | Never weaken a test to pass | `.skip`, loosened assertions, widened types, `any`, `// @ts-ignore`, `catch {}` | fix the code the test guards |
| 6 | Never fix in data | SQL `update` in prod console; hand-edited rows | code handles the scenario; reviewed backfill migration |
| 7 | Run the whole suite, not the one test | "the new test passes" | lint + typecheck + full unit + build; affected e2e |
| 8 | Re-check every caller of changed code | changing a function signature/semantics without grepping | grep; read; adjust or add tests |
| 9 | Don't change behaviour you weren't asked to | "also made it faster", "also handles nulls now" | note it under "parked"; separate PR |
| 10 | No new dependency to fix a bug | adding a library for one guard | stdlib / existing utils |
| 11 | No silent fallbacks | `?? defaultValue` that hides the failure | fail loudly with a typed error; log with requestId |
| 12 | Say what you verified, exactly | "should work now" | command + result table |
| 13 | Stashed-fix check for the regression test | test written after fix, never seen failing | stash, run, see red, pop |
| 14 | Rollback stated | none | redeploy previous tag / flag off / revert migration |
| 15 | Stop when the fix grows | diff > 3 files or > ~60 lines | back to plan gate; it may be a feature or refactor |

## The "would this break something else?" check (run before claiming done)
1. What else calls this? (grep) — read each caller's expectation.
2. What else reads this data/shape? (types, DB columns, API consumers)
3. What was the old behaviour relied on by a test or a UI branch? (run sibling tests)
4. Is there a feature flag, env, or tenant branch that takes the other path? (test that path too)
5. Does the change alter a migration, policy, or env contract? (if yes → supabase-schema-rls / security-review gates apply)
If any answer is "not sure", find out before returning.
