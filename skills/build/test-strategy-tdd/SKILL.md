---
name: test-strategy-tdd
description: Use before implementing any feature, fix or refactor to decide what tests exist and write them first. Produces a test pyramid for the feature type (unit / integration / e2e / contract), Vitest and Playwright scaffolds, fixtures, and a coverage gate, following red→green→refactor. Wraps superpowers test-driven-development and anthropics webapp-testing when installed. Not for test-only debugging (use safe-fix) or CI wiring (use ci-cd-vercel-github).
license: MIT
metadata:
  domain: build
  version: 0.1.0
  author: giri-skills
---

# test-strategy-tdd

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
