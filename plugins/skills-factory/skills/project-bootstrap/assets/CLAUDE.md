# CLAUDE.md — {{PROJECT_NAME}}

How we work in this repo. Read `docs/SPEC.md` (what) and `docs/HANDOFF.md` (where we are) before any task.

## Commands (verify against package.json before relying on them)
| Task | Command |
|---|---|
| Install | `npm ci` |
| Dev | `npm run dev` |
| Lint / typecheck | `npm run lint && npm run typecheck` |
| Unit tests | `npm test` |
| E2E | `npm run test:e2e` |
| Build | `npm run build` |
| Local DB | `supabase start` / `supabase stop` |
| New migration | `supabase migration new <name>` |
| Apply migrations locally | `supabase db reset` |
| Regenerate DB types | `npm run db:types` |
| RLS lint | `python3 -I scripts/rls_lint.py supabase/migrations` |

## Working rules
| # | Rule |
|---|---|
| 1 | Plan before build. For anything touching >3 files, schema, auth or CI: write the plan (files, tests, acceptance) and wait for "go". |
| 2 | Minimal diff. Edit the failing lines; never regenerate a file to change a few lines. |
| 3 | Read before writing. Never assume file contents. |
| 4 | Verify before claiming done: lint, typecheck, unit, build. Paste the command output summary. |
| 5 | Never break one thing fixing another. Run the full unit suite after every fix, not just the new test. |
| 6 | Fix in code, not in data. No SQL patches as fixes. |
| 7 | One topic per thread. End every thread by updating `docs/HANDOFF.md`. |
| 8 | Push only changed files. No whole-tree rewrites, no formatter-only churn in feature PRs. |

## Stack conventions (summary; full text in giri-skills `shared/stack-conventions.md`)
- Data access only via `lib/db` or `server/services`. No Supabase calls in components.
- RLS on every table. Service-role key only server-side. Never `NEXT_PUBLIC_` a secret.
- zod at every boundary (`server/validators`). Services return `Result<T, E>`; never throw across server/client.
- Structured JSON logs via `lib/logger`; no `console.log` in committed code.
- One migration per change, forward-only, with `-- rollback:` block. Never edit an applied migration.
- Tests: unit (vitest) for services/validators; integration for `lib/db` against local Supabase; e2e (playwright) for critical paths. Coverage ≥ 80% on `server/`.

## Gates
```
plan → approve → build → test → verify → handoff
```
A step is not done until its gate output exists (plan table, "go", passing test run, HANDOFF entry).

## Where things live
| What | Where |
|---|---|
| Spec | `docs/SPEC.md` |
| Decisions | `docs/adr/NNNN-title.md` |
| Thread state | `docs/HANDOFF.md` |
| Env contract | `.env.example` |
| CI | `.github/workflows/{ci,preview,prod}.yml` |

## Do not
- Commit secrets, `.env*` files, or generated types with secrets.
- Add dependencies without stating why in the PR.
- Skip the migration rollback block.
- Use `any` to silence the type checker.
