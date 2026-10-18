---
name: project-bootstrap
description: Use when the user starts a new app or repo (Next.js + Supabase + Vercel by default) and needs the enterprise skeleton before any feature code — SPEC.md, CLAUDE.md, HANDOFF.md, ADR folder, GitHub Actions CI skeleton, .env.example contract, branch rules. Produces the docs/CI/ADR scaffold (via scripts/scaffold.py, idempotent) plus a filled SPEC.md and a stack starter checklist. Not for adding features to an existing repo (use spec-to-plan) or pipeline tuning (use ci-cd-vercel-github).
license: MIT
metadata:
  domain: build
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: target, type: path, required: true, from: "project directory to scaffold (created if absent)"}
      - {name: name, type: string, required: true, from: "project name"}
      - {name: multi_tenant, type: flag, required: false, flag: "--multi-tenant", from: "true to mark tenancy as multi-tenant"}
    run:
      - {step: scaffold, kind: script, cmd: "python3 -I scripts/scaffold.py --target {target} --name {name} {multi_tenant}", stdout: "{out}/scaffold.log"}
    outputs:
      - {path: "{target}/docs/SPEC.md", checks: [exists, sections:["Purpose"]]}
      - {path: "{target}/CLAUDE.md", checks: [exists]}
      - {path: "{target}/docs/HANDOFF.md", checks: [exists]}
      - {path: "{target}/docs/adr/0001-stack.md", checks: [exists]}
      - {path: "{target}/.github/workflows/ci.yml", checks: [exists, yaml]}
      - {path: "{target}/.env.example", checks: [exists]}
---

# project-bootstrap

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/project-bootstrap --input <name>=<value> … --out <dir>` (see `--explain build/project-bootstrap`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

## When to use
- "New app", "new repo", "set up the project", "bootstrap", "start from scratch".
- An existing repo has no `docs/SPEC.md`, `CLAUDE.md` or `HANDOFF.md` and the user wants it brought to standard.
- NOT for: feature work (`spec-to-plan`), pipeline changes (`ci-cd-vercel-github`), schema (`supabase-schema-rls`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Project name + one-line purpose | yes | user |
| Target directory | yes | user (default: cwd) |
| Stack deviations from `shared/stack-conventions.md` | no | user |
| Tenancy model (single / multi-tenant) | yes | user — ask once |
| Hosting/accounts already provisioned (Vercel, Supabase, GitHub) | no | user |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../../shared/stack-conventions.md`, `../../../shared/token-efficiency.md`, `../../../shared/quality-bar.md`.
2. **Plan.** List what will be created (see `references/bootstrap-checklist.md`) and what already exists in the target dir. Present as a table: file → create / keep / skip. Wait for "go". *(gate: plan→approve)*
3. **Build.** Run the scaffold — it never overwrites:
   ```
   python3 -I scripts/scaffold.py --target <dir> --name "<project>" [--multi-tenant]
   ```
   It writes `docs/SPEC.md`, `CLAUDE.md`, `docs/HANDOFF.md`, `docs/adr/0000-template.md`, `docs/adr/0001-stack.md`, `.env.example`, `.github/workflows/{ci,preview,prod}.yml`, `.github/CODEOWNERS`, `.github/pull_request_template.md`.
4. Fill `docs/SPEC.md` from the user's inputs: purpose, users, in/out of scope, NFRs, tenancy, open questions marked `[TO BE BASELINED — owner: ___]`.
5. Fill `CLAUDE.md` with the repo's actual commands (install, dev, test, lint, migrate) — verify each command exists in `package.json` before writing it.
6. Write `docs/adr/0001-stack.md` recording the stack decision and any deviations from conventions.
7. **Test.** Run `python3 -I scripts/scaffold.py --target <dir> --name "<project>" --dry-run` a second time; it must report 0 writes (idempotency). Run `bash -n` on any shell scripts and `python3 -c "import yaml"`-free YAML sanity (open each workflow; confirm `on:` and `jobs:` keys). *(gate: build→test)*
8. **Verify.** Walk `references/bootstrap-checklist.md`; every row is Done or has an owner. Apply branch protection rules from `references/branch-rules.md` (give the exact `gh` commands; do not run them without approval). *(gate: test→verify)*
9. Update `docs/HANDOFF.md` with changed files and the next-thread prompt (format in `../../../shared/token-efficiency.md`).

## Output
| Artifact | Path |
|---|---|
| Scaffold | `<dir>/docs/`, `<dir>/CLAUDE.md`, `<dir>/.github/`, `<dir>/.env.example` |
| Filled SPEC | `<dir>/docs/SPEC.md` |
| Stack ADR | `<dir>/docs/adr/0001-stack.md` |
| Branch-protection commands | in chat, copy-paste ready |
| HANDOFF | `<dir>/docs/HANDOFF.md` |

## Self-check
- [ ] Scaffold re-run reports 0 writes (no overwrite, idempotent)
- [ ] Every `CLAUDE.md` command verified against `package.json` / `Makefile`
- [ ] `.env.example` lists every var the workflows reference; no secret values
- [ ] Unknowns carry `[TO BE BASELINED — owner: ___]`
- [ ] No personal or other-client details anywhere in the scaffold
- [ ] HANDOFF.md updated with the next-thread prompt

## References
- `references/bootstrap-checklist.md` — full checklist of files, settings and accounts
- `references/branch-rules.md` — branch protection, naming, PR rules with `gh` commands
- `assets/SPEC.md`, `assets/CLAUDE.md`, `assets/HANDOFF.md`, `assets/adr-template.md`, `assets/env.example`, `assets/workflows/` — templates the scaffold writes
- `scripts/scaffold.py` — idempotent scaffold writer
