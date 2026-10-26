# TDD Method (fallback for superpowers:test-driven-development)

## Loop
| Step | Do | Stop condition |
|---|---|---|
| Red | Write one test for one behaviour from the pyramid table. Run it. | Fails on the assertion (not on import/syntax). If it passes, the behaviour exists or the test is wrong — investigate before continuing. |
| Green | Write the least code that passes. Hard-coding is allowed if the next test will force generalisation. | Test passes; full unit suite still green. |
| Refactor | Remove duplication, name things, extract. No behaviour change. | Suite green after every refactor step. |
| Commit | `test: …` then `feat: …` (or one commit) | — |

## Rules
| Rule | Why |
|---|---|
| Never write a second test while one is red | keeps diagnosis trivial |
| Run the full unit suite before claiming green, not only the current file | collateral breakage shows up here |
| A test that cannot fail is deleted | false confidence |
| Test behaviour through the public function, not private helpers | refactor-safe |
| One assertion concept per test; multiple `expect` fine if same concept | clear failure messages |
| Deterministic: no real time, randomness, network, order dependence | flake-free |
| Test names are sentences a product owner understands | spec doubles as docs |
| Negative tests first when touching auth/tenant | security regressions are the expensive ones |

## Order of tests for a service
1. Happy path returns `ok` with mapped DTO.
2. Validation/business rule failures, each with its error code.
3. Authorization failures (role, tenant).
4. Persistence failures mapped (`CONFLICT`, `NOT_FOUND`).
5. Side effects (audit written, event enqueued) — assert the call, not the implementation.

## Legacy code without tests
1. Characterisation test: capture current behaviour (even if wrong) so refactors are safe.
2. Then write the failing test for the new behaviour.
3. Change; both pass (update the characterisation test only if the old behaviour was the bug, and say so).

## Signals the design is wrong
- Test needs >3 mocks → the unit has too many dependencies; split.
- Test setup > 15 lines → missing builder/fixture.
- Testing requires reaching into private state → wrong boundary.
