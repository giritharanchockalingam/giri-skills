---
name: ci-cd-vercel-github
description: Use for any pipeline work on a Next.js + Supabase app deployed to Vercel via GitHub Actions — "set up CI", "add preview deploys", "deploy to prod", "pipeline is failing", "rollback". Produces ci.yml (lint→typecheck→unit→build), preview.yml (Vercel preview + Playwright), prod.yml (tag-triggered: migrate staging→prod, deploy, smoke, release), environment/secret matrix, promotion flow and a rollback runbook. Not for test authoring (use test-strategy-tdd) or alerting (use observability-setup).
license: MIT
metadata:
  domain: build
  adlc_stage: deploy
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: target, type: path, required: true, from: "repo root (created if absent); existing workflows are kept, never overwritten"}
      - {name: seed, type: dir, required: false, from: "evals/demos only: an existing repo layout copied to target first, so the example is never written to (evals/fixtures/repo-existing-ci)"}
    run:
      - {step: seed, kind: script, cmd: "python3 -I scripts/seed_repo.py --from {seed} --target {target}", skip_if_missing: [seed]}
      - {step: install, kind: script, cmd: "python3 -I scripts/install_ci.py --target {target} --report-json {out}/ci-report.json --report-md {out}/ci-report.md"}
    outputs:
      - {path: "{out}/ci-report.json", checks: [exists, json, contains:"jobs_found"]}
      - {path: "{out}/ci-report.md", checks: [exists, sections:["Workflows","Branch protection","Next steps"]]}
      - {path: "{target}/.github/workflows/ci.yml", checks: [exists, yaml]}
      - {path: "{target}/.github/workflows/preview.yml", checks: [exists, yaml]}
      - {path: "{target}/.github/workflows/prod.yml", checks: [exists, yaml]}
    modes:
      new: {case: agent-happy-path, bring: "an empty or brand-new repo folder"}
      existing: {case: agent-mode-existing, bring: "your repo with its current workflows and package.json"}
---

# ci-cd-vercel-github

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/ci-cd-vercel-github --input <name>=<value> … --out <dir>` (see `--explain build/ci-cd-vercel-github`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. The install step exits 1 when a kept (customised) workflow lacks a required job, because branch protection depends on those check names; merge the missing stage from `assets/workflows/` and re-run.

## Starting points
- **New** — point `target` at an empty folder: all three workflows are written from `assets/workflows/` and validated.
- **Existing** — point `target` at your repo: customised workflows are kept and validated job by job, missing ones are added, and every `npm run` they call is checked against your package.json.

## When to use
- New pipeline, pipeline change, flaky/failing workflow, adding a stage (e2e, RLS lint, coverage gate), release/rollback procedure.
- NOT for: writing tests (`test-strategy-tdd`), runtime alerts (`observability-setup`), bootstrap of a brand-new repo (`project-bootstrap` calls this skill's assets).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Goal (new pipeline / add stage / fix failure / rollback) | yes | user |
| Existing `.github/workflows/*`, `package.json` scripts | yes | repo |
| Environments: Vercel project, Supabase project refs (staging, prod) | yes for prod work | user — ask once |
| Failing run URL / logs | yes for fixes | user |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../../shared/stack-conventions.md` (CI row), `../../../shared/token-efficiency.md`. Read existing workflows and `package.json` scripts; map what runs where today.
2. **Plan.** Stage table (from `references/pipeline-stages.md`): stage → trigger → job → required check name → secrets. For fixes: failing step → root cause hypothesis → minimal change. Post; wait for "go". *(gate: plan→approve)*
3. **Build.** Copy/merge `assets/workflows/ci.yml`, `assets/workflows/preview.yml`, `assets/workflows/prod.yml`; never overwrite a customised workflow — diff and merge. Confirm every `npm run <script>` exists. Fill the env/secret matrix from `references/env-promotion.md`; list `gh secret set` commands (values never in chat).
4. **Branch protection.** Required checks = `ci / lint-typecheck-test`, `ci / rls-lint`, `preview / e2e`. Commands in `project-bootstrap/references/branch-rules.md`.
5. **Test.** Validate YAML (`python3 -c "import yaml"`-free: open each file; check `on:`/`jobs:`), run `act` if available or push a `chore/ci` branch and watch the run; confirm check names match protection. *(gate: build→test)*
6. **Prod path.** Walk `references/env-promotion.md`: GitHub Environments `staging` and `production` (required reviewers on production), tag → migrate staging → migrate prod → deploy → smoke → release. Dry-run with a `v0.0.0-rc` tag against staging only if the user approves.
7. **Rollback.** Install `references/rollback.md` as `docs/runbooks/rollback.md`; confirm the previous deployment is promotable (`vercel rollback` or Vercel "Instant Rollback") and the migration revert path exists.
8. **Verify.** One PR shows green `ci` + `preview` and a comment with the preview URL; one tag (rc) runs `prod.yml` to the staging gate. *(gate: test→verify)*
9. Update `docs/HANDOFF.md`.

## Output
| Artifact | Path |
|---|---|
| Workflows | `.github/workflows/ci.yml`, `preview.yml`, `prod.yml` |
| Env/secret matrix | `docs/ci-cd.md` §Environments (from `references/env-promotion.md`) |
| Rollback runbook | `docs/runbooks/rollback.md` |
| Branch-protection commands | chat |

## Self-check
- [ ] Every stage has a required-check name that matches branch protection
- [ ] Secrets only via GitHub secrets / Vercel env; none echoed in logs (`::add-mask::` where derived)
- [ ] `concurrency` set on every workflow; prod never cancels in progress
- [ ] Prod deploy only from tag on `main`; verified by `git merge-base`
- [ ] Migrations run before deploy, staging before prod, with the production Environment gate
- [ ] Smoke hits `/api/health` and `/api/health/deep` after deploy
- [ ] Rollback runbook tested once (previous deployment promoted)

## References
- `references/pipeline-stages.md` — stages, jobs, check names, caching, timeouts
- `references/env-promotion.md` — environment matrix, secrets, promotion flow, Vercel settings
- `references/rollback.md` — code and migration rollback procedures, decision table
- `references/troubleshooting.md` — common failures and fixes
- `assets/workflows/ci.yml`, `assets/workflows/preview.yml`, `assets/workflows/prod.yml`
- `scripts/install_ci.py` — writes absent workflows, keeps existing ones, validates `on:`/`jobs:` and required job names
