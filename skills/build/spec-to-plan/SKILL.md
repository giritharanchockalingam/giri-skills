---
name: spec-to-plan
description: Use when a feature request, ticket or SPEC section must become an executable plan before any code is written. Produces a task-gated plan (docs/plans/<slug>.md) with files to touch, acceptance criteria, test list, rollback, and explicit plan→approve→build→test→verify gates. Wraps the superpowers brainstorm/write-plan skills when installed. Not for bug fixes (use safe-fix) or product definition (use product-spec-prd).
license: MIT
metadata:
  domain: build
  version: 0.1.0
  author: giri-skills
---

# spec-to-plan

## When to use
- "Plan this feature", "how should we build X", a ticket or SPEC section is handed over for implementation.
- Any change touching >3 files, schema, auth, CI, or billing — the plan gate is mandatory.
- NOT for: bugs (`safe-fix`), product definition (`product-spec-prd`), repo setup (`project-bootstrap`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Feature description or SPEC section / ticket | yes | user / `docs/SPEC.md` |
| Repo access (to read current structure) | yes | repo |
| Constraints (deadline, no-schema-change, flag-gated, etc.) | no | user |
| `docs/HANDOFF.md` state | yes if exists | repo |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../../shared/token-efficiency.md`, `../../../shared/stack-conventions.md`, `../../../shared/quality-bar.md`, then `docs/SPEC.md`, `CLAUDE.md`, `docs/HANDOFF.md` in the repo.
2. **Clarify (brainstorm).** If the upstream skill `superpowers:brainstorming` is installed (see VENDORED.md), invoke it for this step; otherwise follow `references/brainstorm-fallback.md`. Output: ≤5 open questions, each with your default answer. Ask once. *(gate: plan inputs)*
3. **Map the change.** Read every file the change touches. Produce the file table: path → create/modify → why. Flag anything that violates `shared/stack-conventions.md`.
4. **Write the plan.** If `superpowers:writing-plans` is installed, invoke it and then apply the gates below; otherwise use `assets/plan-template.md` directly and follow `references/plan-method.md`. Every task has: files, acceptance criterion, test(s), estimate (S/M/L), rollback.
5. **Risk and rollback.** Fill the risk table (schema, auth, data migration, external API). Each risk: mitigation + owner. Rollback must be concrete (revert tag, disable flag, down-migration).
6. **Present and stop.** Post the plan summary (≤10 lines + link to `docs/plans/<slug>.md`). Wait for "go". *(gate: plan→approve)*
7. **Execute in task order** after approval. Per task: build → run its tests → run the full unit suite → mark done in the plan file. If `superpowers:executing-plans` is installed, invoke it for the loop. *(gates: build→test→verify)*
8. **Verify.** All acceptance criteria checked, lint/typecheck/unit/build green, e2e for touched critical paths. Paste the command summary.
9. Update `docs/HANDOFF.md` (changed files, open items, next-thread prompt).

## Output
| Artifact | Path |
|---|---|
| Plan | `docs/plans/<yyyy-mm-dd>-<slug>.md` (from `assets/plan-template.md`) |
| Plan summary | chat, ≤10 lines |
| Post-build verification | chat, command output summary |
| HANDOFF | `docs/HANDOFF.md` |

## Self-check
- [ ] Every task has files, acceptance criterion, test, rollback
- [ ] No code written before "go"
- [ ] File table came from reading the repo, not memory
- [ ] Schema changes route to `supabase-schema-rls`; auth/RLS changes get `security-review` as a task
- [ ] Plan fits one thread; if not, split and say so
- [ ] Unknowns marked `[TO BE BASELINED — owner: ___]`

## References
- `references/plan-method.md` — task decomposition rules, sizing, gate definitions
- `references/brainstorm-fallback.md` — question method when superpowers is absent
- `assets/plan-template.md` — plan file template
