# Safe-Fix Method (fallback for superpowers:systematic-debugging)

## 1. Reproduce
| Technique | When |
|---|---|
| Failing unit test with the exact input | logic bugs; preferred form |
| Integration test against local Supabase with seed persona | RLS, query, auth bugs |
| `curl` / Playwright script with recorded request | route handlers, actions, prod-only |
| Replay from logs by `requestId` | prod incidents — pull the log lines, rebuild inputs |
| Env parity check | "works locally": diff `.env.example` vs Vercel env; node version; `VERCEL_ENV` branches in code |

Rules: deterministic (fixed time, seed, ids); minimal (strip inputs until it stops failing, then add the last one back); recorded (the test file or the command is in the report).
If no repro after 30 min: write down what was tried, add targeted logging (`log.debug` with ids, behind `LOG_LEVEL`), ship that, wait for the next occurrence. Do not guess-fix.

## 2. Isolate
| Step | Do |
|---|---|
| Read the error literally | the message names the file:line and the value. Read that line and its inputs before theorising. |
| Trace backwards | from the failing line to where the bad value was produced; cite file:line at each hop |
| Bisect | `git bisect run <repro>` between last-good tag and HEAD; or bisect inputs; or bisect layers (replace service with stub → does page still fail?) |
| Differential | what differs between working and failing case: env, role, tenant, data shape, time, concurrency |
| Confirm | change one thing that your hypothesis says will fix it (even a temporary hack) → repro passes → hypothesis confirmed. Then revert the hack and do the real fix. |

Root cause sentence: "`<file:line>` does X when Y because Z; the symptom appears at `<file:line>`." Trigger ≠ cause: "deploy on Tuesday" is the trigger; "unawaited promise in service" is the cause.

## 3. Minimal diff
| Allowed | Not allowed |
|---|---|
| change the broken expression / branch / guard | reformat the file |
| add a missing `await`, null check, tenant filter, `with check` | rename variables "for clarity" |
| add a zod rule | restructure the module |
| add one helper if the fix needs it twice | move code between files |
| extend an existing test file | delete or `.skip` tests |

Litmus: every changed line is explained by the root cause sentence. If not, it is a separate PR.

## 4. Regression test
- Name after the bug: `it('keeps tenant filter when status filter is empty (#412)')`.
- Place next to existing tests for that unit.
- Verify it fails on old code: `git stash` the fix → run → fails → `git stash pop` → run → passes. Say so in the report.
- For prod incidents, also add the e2e if the path is critical.

## 5. Verify the whole
| Check | Command |
|---|---|
| lint | `npm run lint` |
| typecheck | `npm run typecheck` |
| full unit | `npm test` |
| integration (if db/rls touched) | `npm test -- --project integration` |
| e2e for touched path | `npm run test:e2e -- tests/e2e/<flow>.spec.ts` |
| build | `npm run build` |
| callers | `grep -rn "<changedFn>(" --include=*.ts --include=*.tsx .` → read each |
| behaviour of adjacent branches | run the sibling tests of the unit; manual check of the opposite case |

Paste the summary table in the report. "Tests pass" without the command is not verification.

## 6. Data produced by the bug
1. Fix the code (above).
2. Quantify: `select count(*) …` of affected rows (read-only).
3. Write a reviewed backfill migration (idempotent, batched) per `supabase-schema-rls/references/migration-format.md`.
4. Test on staging with a copy; apply via release.
Never: `update` from a SQL console as "the fix".

## 7. Report
Use `assets/fix-report.md`. Keep it to one screen.
