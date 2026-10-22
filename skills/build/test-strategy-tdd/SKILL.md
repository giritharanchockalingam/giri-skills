---
name: test-strategy-tdd
description: Use before implementing any feature, fix or refactor to decide what tests exist and write them first, and to add testing to a repo that has none — "set up the tests first", "add testing for the login flow" in a repo with no vitest or playwright, "scaffold the tests for <feature>", "write the tests for these files", "there is already a test for X; regenerate it from the template" (existing tests are never overwritten). Produces a test pyramid per acceptance criterion (unit / integration / e2e / contract) with negative cases, Vitest and Playwright configs and red stubs via scripts/scaffold_tests.py, fixtures, and an 80% coverage gate on server/, following red→green→refactor. Wraps superpowers test-driven-development and anthropics webapp-testing when installed. Not for test-only debugging (use safe-fix), CI wiring (use ci-cd-vercel-github), generating pytest-playwright flows from a flow list (webapp-testing-runner) or planning the feature itself (spec-to-plan).
license: MIT
metadata:
  domain: build
  adlc_stage: evaluate
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: feature, type: md, required: true, from: "feature.md: H1 title + one bullet per acceptance criterion (from spec-to-plan or the user)"}
      - {name: files, type: string, required: true, from: "comma-separated repo-relative source files the feature touches"}
      - {name: target, type: path, required: true, from: "repo root (tests/ created under it; existing tests never overwritten)"}
      - {name: dry_run, type: flag, required: false, flag: "--dry-run", from: "true to report only and write nothing"}
      - {name: seed, type: dir, required: false, from: "evals/demos only: an existing repo layout copied to target first, so the example is never written to (evals/fixtures/repo-existing-suite)"}
    run:
      - {step: seed, kind: script, cmd: "python3 -I scripts/seed_repo.py --from {seed} --target {target}", skip_if_missing: [seed]}
      - {step: scaffold, kind: script, cmd: "python3 -I scripts/scaffold_tests.py {feature} --files {files} --target {target} {dry_run} --report {out}/scaffold-report.json --plan {out}/test-plan.md"}
    outputs:
      - {path: "{out}/scaffold-report.json", checks: [exists, json, contains:"written"]}
      - {path: "{out}/test-plan.md", checks: [exists, sections:["Pyramid","Criteria map","Red"]]}
    modes:
      new: {case: agent-happy-path, bring: "the feature's acceptance criteria and the files it touches"}
      existing: {case: agent-mode-existing, bring: "your repo with the tests it already has"}
---

# test-strategy-tdd

## In a conversation: write the tests now
The reply **is the test plan and the red tests** (or one ask), never only a command or "next: generate stubs". About 1,000 tokens, tables and short code. Never claim a test ran: give the exact command and the expected red/green result.

**Never**
- Never overwrite an existing test or config — even when asked to "regenerate it from the template": the existing file is **kept, read and listed under skipped**; criteria it does not cover are listed to add by hand. In a dry run nothing is written.
- Never mock the service under test; mock only I/O at the boundary (DB client, network, clock).
- Never write generic tests without the feature: no feature/acceptance criteria → ask once for the feature or change and its acceptance criteria, and stop.
- Never use `waitForTimeout`, CSS classes or nth-child in Playwright.

**Which reply**
1. **Feature described** (e.g. invoice creation: validator, service, server action, page), in this order:
   a. **Pyramid table** `| Acceptance criterion | Layer | Test file | Fixture |` (validator → unit; service → unit + integration; query → integration; server action → unit; page → e2e `tests/e2e/<flow>.spec.ts`).
   b. **Negative cases, each a row**: invalid input, **viewer (forbidden role)**, **cross-tenant** (RLS denies), not-found, duplicate (e.g. duplicate invoice number).
   c. **Mocking**: only I/O boundaries mocked; the service under test is real.
   d. **Red**: one or two key tests in code, then "Run `npx vitest run <files>` — must fail on the assertion, not an import error, before any implementation."
   e. **Green → refactor**: minimum code to pass; then **the full suite** `npm test`.
   f. **Coverage gate**: `npm test -- --coverage` — **≥ 80% on `server/`**, reported as `criterion → test → status`.
2. **Repo with no vitest/playwright**: scaffold from `assets/` without overwriting anything that exists — `vitest.config.ts`, `playwright.config.ts`, `tests/setup.ts` (from `assets/tests-setup.ts`), `tests/e2e/auth.setup.ts` (from `assets/e2e-auth.setup.ts`; storageState per role in `tests/e2e/.auth/<role>.json`, gitignored) — and **add `package.json` scripts** `"test": "vitest run"`, `"test:e2e": "playwright test"`. Then the login e2e: accessible selectors (`getByRole`, `getByLabel`), `test.use({ storageState })` for signed-in cases, web-first assertions, **no `waitForTimeout`**; negative case for wrong password.
3. **Files given** (feature.md + files + target): name the command and outputs — `python3 -I scripts/scaffold_tests.py feature.md --files <a,b,…> --target <repo> [--dry-run] --report scaffold-report.json --plan test-plan.md` — then the result per file: `server/**`, `lib/**` and other `.ts` → vitest `it.todo` stub per criterion at `tests/unit/<path-with-dashes>.test.ts`; `app/**/page.tsx` → Playwright `test.fixme` spec at `tests/e2e/<slug>.spec.ts`; `components/**` → **listed for a manual component test, nothing written**; existing test files → **skipped (kept)** and matched to criteria (covered vs to add). Show the pyramid table from `test-plan.md` and the `scaffold-report.json` counts (written, skipped, components, would_write). Feature file missing → ask once for the feature description with acceptance criteria (exit 1).

## Starting points
- **New** — red stubs are written for every file the feature touches (vitest `it.todo`, Playwright `test.fixme`), with the pyramid and criteria map in `test-plan.md`.
- **Existing** — test files you already have are kept, read and matched to the acceptance criteria; the plan lists which criteria they already cover and which to add, and stubs are written only where no test file exists.

## When to use
- "Write tests for", "how should we test", "add coverage", before any task from `spec-to-plan`.
- Setting up `vitest` / `playwright` in a repo that has none.
- NOT for: diagnosing a failing test (`safe-fix`), pipeline (`ci-cd-vercel-github`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Feature / change description with acceptance criteria | yes | plan / user |
| Feature type: service, query, server action, page, API route, edge function, migration | yes | infer from plan; ask if unclear |
| Existing test setup (`vitest.config.ts`, `playwright.config.ts`, `tests/`) | yes | repo |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../../shared/stack-conventions.md` (Tests row) and `../../../shared/token-efficiency.md`. Read existing configs and one existing test per layer to match style.
2. **Plan the pyramid.** Using `references/test-pyramid.md`, produce the table: acceptance criterion → test layer → file → fixture. Include negative and RLS cases. Post it; wait for "go". *(gate: plan→approve)*
3. **Scaffold** missing config from `assets/` (vitest.config.ts, playwright.config.ts, setup files, fixtures dir). Do not overwrite existing configs; diff and merge.
4. **Red.** Write the tests first. Run them; they must fail for the right reason (assertion, not import error). If the upstream skill `superpowers:test-driven-development` is installed (see VENDORED.md), invoke it for steps 4–6; otherwise follow `references/tdd-method.md`.
5. **Green.** Implement the minimum to pass. No extra behaviour.
6. **Refactor** with tests green after each step. Run the full unit suite, not just the new file. *(gate: build→test)*
7. **E2E.** For page/flow changes: Playwright spec from `references/playwright-patterns.md`. If `anthropics:webapp-testing` is installed, invoke it to drive the browser; otherwise follow the patterns file.
8. **Verify.** Coverage ≥ 80% on `server/` (`npm test -- --coverage`); report the table: criterion → test → status. *(gate: test→verify)*
9. Update `docs/HANDOFF.md`.

## Output
| Artifact | Path |
|---|---|
| Pyramid table | chat + top of the plan file |
| Unit/integration tests | `tests/unit/**`, `tests/integration/**` |
| E2E | `tests/e2e/<flow>.spec.ts` |
| Configs | `vitest.config.ts`, `playwright.config.ts`, `tests/setup.ts` |
| Fixtures | `tests/fixtures/**` |

## Self-check
- [ ] Every acceptance criterion maps to ≥1 test; every test maps to a criterion
- [ ] Tests written before implementation and seen failing first
- [ ] Negative cases: invalid input, forbidden role, cross-tenant, not-found
- [ ] No test depends on another test's state; DB tests reset
- [ ] Full suite green, coverage gate met
- [ ] No mocking of the thing under test; mock only I/O at the boundary

## References
- `references/test-pyramid.md` — layer per feature type, what to mock, fixtures
- `references/tdd-method.md` — red/green/refactor rules (fallback for superpowers)
- `references/playwright-patterns.md` — auth, tenant, selectors, flake control (fallback for webapp-testing)
- `assets/vitest.config.ts`, `assets/playwright.config.ts`, `assets/tests-setup.ts`, `assets/e2e-auth.setup.ts`, `assets/unit-test.example.ts`, `assets/e2e-test.example.ts`
- `scripts/scaffold_tests.py` — feature.md + file list → vitest `it.todo` stubs and Playwright `test.fixme` specs, never overwriting

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/test-strategy-tdd --input <name>=<value> … --out <dir>` (see `--explain build/test-strategy-tdd`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. Stubs are `it.todo` / `test.fixme` per criterion — red first; replace each with a failing test before implementing.
