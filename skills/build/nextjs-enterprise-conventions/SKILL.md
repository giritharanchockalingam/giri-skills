---
name: nextjs-enterprise-conventions
description: Use whenever writing or reviewing Next.js (App Router) / React / TypeScript code in this stack. Enforces server/client component rules, data-access layering (lib/db, server/services, server/actions), zod at boundaries, the typed Result<T,E> error pattern, structured logging, folder and naming conventions from shared/stack-conventions.md, and Vercel's react/next best-practice skills when installed. Produces compliant code plus a conventions checklist result. Not for schema (use supabase-schema-rls) or security audits (use security-review).
license: MIT
metadata:
  domain: build
  adlc_stage: build
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: target, type: dir, required: true, from: "Next.js repo root (app/, components/, lib/, server/)"}
    run:
      - {step: lint, kind: script, cmd: "python3 -I scripts/lint_conventions.py --target {target} --findings {out}/findings.csv --report {out}/report.md"}
    outputs:
      - {path: "{out}/findings.csv", checks: [exists, csv:[rule,file,line,snippet,severity]]}
      - {path: "{out}/report.md", checks: [exists, sections:["Summary","Findings","Rules"]]}
---

# nextjs-enterprise-conventions

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/nextjs-enterprise-conventions --input <name>=<value> … --out <dir>` (see `--explain build/nextjs-enterprise-conventions`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. The lint step exits 1 on any high-severity finding, so a non-compliant repo fails the run by design; fix the findings in code, then re-run.

## When to use
- Any new or modified file under `app/`, `components/`, `lib/`, `server/`.
- "Review this component", "is this the right place for this query", "add a server action", "add a page".
- Invoked by `spec-to-plan` tasks and `safe-fix` when the diff touches Next.js code.
- NOT for: schema/RLS (`supabase-schema-rls`), security audit (`security-review`), tests design (`test-strategy-tdd`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| The task or diff | yes | user / plan |
| Repo (`CLAUDE.md`, `lib/`, `server/`, existing patterns) | yes | repo |
| Next.js major version (`package.json`) | yes | repo |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../../shared/stack-conventions.md` and `../../../shared/token-efficiency.md`. Read `package.json` for the Next.js version and existing `lib/result.ts`, `lib/logger.ts`, `lib/env.ts` — reuse, never duplicate.
2. **Plan.** For a new feature slice, list files by layer (validator → service → action/route → component → page) with the server/client decision per component. For a review, list the files and the rule IDs you will check. Wait for "go" on anything touching >3 files. *(gate: plan→approve)*
3. **Framework rules.** If the upstream skills `vercel-react-best-practices` and `vercel-composition-patterns` are installed (see VENDORED.md), invoke them for this step; otherwise follow `references/framework-rules.md` (server/client boundaries, caching, data fetching, server actions, routing).
4. **Layering and errors.** Apply `references/layering.md` (what lives where, import direction) and `references/error-result-pattern.md` (`Result<T,E>`, error codes, no throws across the boundary).
5. **Logging.** Apply `references/logging.md`: `lib/logger` only, correlation id from headers, no PII, no `console.log`.
6. **Build.** Write code in minimal diffs. Each server action: zod parse → auth/tenant check → service call → `Result` → typed response. Each component: server by default; `"use client"` only for interactivity, with the reason in a comment.
7. **Test.** Unit for validators/services; component tests for client components with logic; e2e for the page path. Run lint, typecheck, full unit suite. *(gate: build→test)*
8. **Verify.** Walk `references/conventions-checklist.md`; report as a table (rule → pass/fail/n.a. → file:line). Fix fails before returning. *(gate: test→verify)*
9. Update `docs/HANDOFF.md`.

## Output
| Artifact | Form |
|---|---|
| Code | minimal diffs in the layered locations |
| Conventions table | chat: rule → status → location |
| Tests | `tests/unit/**`, `tests/e2e/**` |

## Self-check
- [ ] No Supabase call outside `lib/db` / `server/services`
- [ ] Every server action and route handler parses input with zod and checks auth before work
- [ ] Services return `Result<T,E>`; no `throw` crosses server→client; errors have stable codes
- [ ] `"use client"` only where needed, with reason; no secrets or server-only imports in client files
- [ ] Logs structured via `lib/logger`, with `requestId`; no `console.log`, no PII
- [ ] Names and folders match `shared/stack-conventions.md`
- [ ] lint + typecheck + unit green; e2e for touched pages

## References
- `references/framework-rules.md` — server/client components, caching, fetching, actions, routing (fallback for Vercel skills)
- `references/layering.md` — folder/layer rules, import direction, naming
- `references/error-result-pattern.md` — `Result<T,E>`, error codes, boundary mapping
- `references/logging.md` — log schema, correlation id, redaction
- `references/conventions-checklist.md` — rule table used in verify
- `assets/result.ts`, `assets/server-action.example.ts`, `assets/service.example.ts` — starters
- `scripts/lint_conventions.py` — offline linter for NX1–NX5 (Supabase in components, console.log, zod at actions, service-role exposure, raw SQL); exit 1 on high findings
