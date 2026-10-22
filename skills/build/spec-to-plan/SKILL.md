---
name: spec-to-plan
description: Use when a feature request, ticket or SPEC section must become an executable plan before any code is written — "plan the <feature> from SPEC section 3.4", "plan the whole <module>" (e.g. billing — plans, Stripe, invoices, dunning, admin UI), "how should we build X", or work too big for one thread that must be split into ordered plans. Produces a task-gated plan (docs/plans/<slug>.md) with files to touch, acceptance criteria, test list, rollback, and explicit plan→approve→build→test→verify gates. Wraps the superpowers brainstorm/write-plan skills when installed. Do not use for designing the tenant, roles, plan/entitlement or audit-log model (multi-tenant-saas-patterns), bug fixes (safe-fix), product definition (product-spec-prd) or writing, scaffolding or regenerating tests (test-strategy-tdd).
license: MIT
metadata:
  domain: build
  adlc_stage: requirements
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: spec, type: md, required: true, from: "docs/SPEC.md (or a ticket exported to Markdown)"}
      - {name: section, type: string, required: true, from: "heading text of the SPEC section to plan"}
      - {name: slug, type: string, required: false, from: "plan slug (default: from the heading)"}
      - {name: repo, type: dir, required: false, from: "root of the existing codebase the plan changes; each named file is marked modify/create and migrations are checked"}
    run:
      - {step: plan, kind: script, cmd: "python3 -I scripts/plan.py {spec} --section {section} [--slug {slug}] [--repo {repo}] --template assets/plan-template.md --out {out}/plan.md --tasks {out}/tasks.csv"}
    outputs:
      - {path: "{out}/plan.md", checks: [exists, sections:["Tasks","Gates","Rollback"]]}
      - {path: "{out}/tasks.csv", checks: [exists, csv:[id,task,acceptance,test,rollback,files,size], csv_rows:test!empty, csv_rows:rollback!empty]}
    modes:
      new: {case: agent-happy-path, bring: "the SPEC section for a feature not built yet"}
      existing: {case: agent-mode-existing, bring: "the SPEC section and the repo it changes"}
---

# spec-to-plan

## In a conversation: write the plan now
- **The request names the feature** (SPEC section, ticket, scope): answer **in this reply** with, in order: (1) the context read first — `docs/SPEC.md` (the named section), `CLAUDE.md`, `docs/HANDOFF.md` — and what each contributes, or `[TO BE BASELINED — owner: ___]` where their contents are not in the conversation; (2) at most 5 clarifying questions in one round, each with your default answer, then plan on the defaults; (3) the plan for `docs/plans/<yyyy-mm-dd>-<slug>.md`: file table (path → create/modify → why); ordered tasks, each with files, acceptance criterion, test(s), size S/M/L and rollback; a risk table (risk → mitigation → owner); a concrete rollback (revert tag, flag off, down-migration). Cross-cutting work the SPEC implies gets its own task — an audit-log write when the feature must be audited, an RLS negative test (another tenant's user gets nothing) when data is tenant-scoped, a `security-review` task when auth or RLS changes; (4) a closing line: no code is written until you reply "go". Never reply with only a request for the SPEC.
- **Too big for one thread** (more than ~8 tasks, or several sub-systems such as plans, Stripe, invoices, dunning, admin UI): do not write one long plan. Split it into separate plans, one per thread; list them in build order with the dependency that sets the order, say which plan comes first and why, and give only that first plan's outline. Do not start building.
- **No feature named** ("make a plan for the new feature"): ask once which feature or SPEC section, and stop; do not invent scope or tasks.
- **Asked to fill in tests or rollbacks a thin SPEC does not state**: decline in one line (invented acceptance criteria are not the team's), still list the tasks, and mark their acceptance, tests and rollback `[TO BE BASELINED — owner: Tech lead]`.

## Starting points
- **New** — the SPEC section becomes a task-gated plan: tasks with acceptance, tests, rollback, files and size; anything the SPEC does not say is an owned TBD.
- **Existing** — add `repo`: every file a task names is looked up and marked modify or create, a task that edits an applied migration or numbers a new one out of order is flagged in a "Repo check" section before approve.

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

Missing facts do not stop the plan: mark them `[TO BE BASELINED — owner: ___]` and ask at the end. Only when no feature or SPEC section is named, ask once which one and stop.

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
- `scripts/plan.py` — SPEC section → plan.md (tasks, gates, rollback) + tasks.csv; unknown fields marked `[TO BE BASELINED — owner: ___]`

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs above, then run `python3 scripts/run_skill.py build/spec-to-plan --input <name>=<value> … --out <dir>` (see `--explain build/spec-to-plan`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. Fields the SPEC does not state come out as `[TO BE BASELINED — owner: ___]`; fill them (or the SPEC) before asking for the approve gate.
