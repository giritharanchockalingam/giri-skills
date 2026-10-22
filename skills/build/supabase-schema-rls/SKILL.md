---
name: supabase-schema-rls
description: Use for any Supabase data-model or auth change — new table, column, relationship, role, or policy. Produces a forward-only migration SQL with a rollback block, RLS policies (tenant / owner / role-based / public-read patterns), regenerated typed client, seed data, and an RLS lint pass (scripts/rls_lint.py). Enforces RLS on every table and service-role use server-side only. Not for app-level authz logic (use nextjs-enterprise-conventions) or a full security audit (use security-review).
license: MIT
metadata:
  domain: build
  adlc_stage: build
  version: 0.2.0
  author: giri-skills
  fits:
    stacks: [supabase]
    request_kinds: [feature, hardening, migration, greenfield]
  agent:
    inputs:
      - {name: migrations, type: dir, required: true, from: "supabase/migrations directory (or a single .sql file)"}
      - {name: client_dirs, type: args, required: false, from: "dirs/files that must not reference the service role, e.g. \"app components\""}
      - {name: root, type: path, required: false, from: "repo root for client_dirs"}
      - {name: applied_through, type: string, required: false, from: "file name of the last migration already applied (e.g. 0002_tenancy.sql); no missing-rollback finding for applied ones"}
    run:
      - {step: lint, kind: script, cmd: "python3 -I scripts/rls_lint.py {migrations} [--client-dirs {client_dirs}] [--root {root}] [--applied-through {applied_through}]", stdout: "{out}/rls-lint.txt", expect_exit: [0, 1]}
    outputs:
      - {path: "{out}/rls-lint.txt", checks: [exists, contains:"errors", cmd:"python3 -I scripts/rls_lint.py {migrations} --quiet --applied-through={applied_through}"]}
    modes:
      new: {case: agent-happy-path, bring: "the first migration of your new schema"}
      existing: {case: agent-mode-existing, bring: "your existing migrations folder and app code"}
---

# supabase-schema-rls

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/supabase-schema-rls --input <name>=<value> … --out <dir>` (see `--explain build/supabase-schema-rls`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

## Starting points
- **New** — your first migrations are linted against every rule (RLS on, policies present, tenant predicate, `with check`, roles, rollback block).
- **Existing** — the whole history is replayed in order: policies later dropped or replaced and tables later dropped are judged by what is live now, columns added later count, client code is scanned for the service role, and migrations already applied (`applied_through`) are not asked for a rollback block they can no longer get.

## When to use
- "Add a table", "add a column", "who can see X", "set up RLS", "new role", "migration", "seed".
- Any task from `spec-to-plan` tagged risk = schema or auth.
- NOT for: application authz in server actions (`nextjs-enterprise-conventions`), full review (`security-review`), tenant/RBAC design (`multi-tenant-saas-patterns` — design first, then come here).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Entity description: columns, relationships, tenant-scoped? owner column? | yes | user / plan |
| Access rules per role (who reads / writes / deletes) | yes | user / RBAC matrix |
| Existing schema (`supabase/migrations/`, `lib/db/types.ts`) | yes | repo |
| JWT claim layout (`tenant_id`, `role` in `app_metadata`?) | yes | repo (`auth.jwt()` usage) — ask once if absent |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../../shared/stack-conventions.md` (Migrations, Auth, Multi-tenant rows) and `../../../shared/token-efficiency.md`. Read the latest 3 migrations and `lib/db/types.ts` for naming and claim conventions.
2. **Plan.** Table: entity → columns → indexes → policies (per role × operation) → rollback. Mark destructive changes and propose expand/contract across two releases. Post the table; wait for "go". *(gate: plan→approve)*
3. **Build the migration** with `supabase migration new <name>` and `references/migration-format.md`. Rules: `enable row level security` on every table; `tenant_id` first in composite indexes; `updated_at` trigger; `-- rollback:` block at the end.
4. **Write policies** from `references/rls-patterns.md` — one policy per operation per role; `using` for read/delete, `with check` for insert/update; wrap `auth.*` calls in `(select …)` for performance. Use `assets/rls-policies.sql` snippets.
5. **Lint.** `python3 -I scripts/rls_lint.py supabase/migrations --client-dirs app components lib/supabase/browser.ts`. Zero findings or each one justified in the plan.
6. **Test.** `supabase db reset` locally; run integration tests from `references/rls-testing.md`: for each policy a positive case and a negative case (other tenant / other owner / lower role). Run the full unit suite. *(gate: build→test)*
7. **Types + seed.** `npm run db:types`; update `supabase/seed.sql` with minimal rows for two tenants so negative tests have data.
8. **Verify.** Diff `lib/db/types.ts`; confirm no `service_role` client in `app/`, `components/`, or browser client; confirm `security definer` functions have `set search_path = ''`. *(gate: test→verify)*
9. Update `docs/HANDOFF.md`; if an applied migration was wrong, write a new migration — never edit the applied one.

## Output
| Artifact | Path |
|---|---|
| Migration | `supabase/migrations/<ts>_<name>.sql` (with rollback block) |
| Policies | inside the migration; snippets from `assets/rls-policies.sql` |
| Lint result | chat, from `scripts/rls_lint.py` |
| Integration tests | `tests/integration/rls/<table>.test.ts` |
| Types | `lib/db/types.ts` regenerated |
| Seed | `supabase/seed.sql` |

## Self-check
- [ ] Every new table: `enable row level security` + at least one policy, or an explicit "no access by design" comment
- [ ] Every tenant table: `tenant_id not null` + policy predicate on it + index leading with it
- [ ] `with check` present on every insert/update policy (not only `using`)
- [ ] No `service_role` in client code; `security definer` functions pin `search_path`
- [ ] Rollback block reverses every statement in reverse order
- [ ] Positive + negative integration test per policy, all green
- [ ] Applied migrations untouched

## References
- `references/rls-patterns.md` — tenant, owner, role-based, public-read patterns; bypass mistakes
- `references/migration-format.md` — file layout, naming, rollback block, expand/contract
- `references/rls-testing.md` — integration test method with JWT impersonation
- `assets/rls-policies.sql` — copy-paste policy snippets
- `assets/migration-template.sql` — migration skeleton
- `scripts/rls_lint.py` — offline linter
