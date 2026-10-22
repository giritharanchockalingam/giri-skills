---
name: ci-cd-vercel-github
description: Use for any pipeline work on a Next.js + Supabase app deployed to Vercel via GitHub Actions — "set up CI", "PR checks", "add preview deploys", "tag-based prod releases with migrations", "deploy to prod", "pipeline is failing", a failed workflow run or step in ci.yml/preview.yml/prod.yml (e.g. supabase db push failing on a migration checksum), "rollback". Produces ci.yml (lint→typecheck→unit→build), preview.yml (Vercel preview + Playwright), prod.yml (tag-triggered: migrate staging→prod, deploy, smoke, release), environment/secret matrix, promotion flow and a rollback runbook. Do not use for application bugs outside the pipeline (safe-fix), test authoring (test-strategy-tdd) or alerting (observability-setup).
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
      - {name: deploy, type: string, required: false, from: "vercel|skip — override the deploy-target detection: `vercel` forces preview.yml/prod.yml even when the repo deploys elsewhere, `skip` never writes them; omitted = detect from existing workflows/config (AWS, Azure, GCP, Fly.io, Railway → the Vercel deploy workflows are not written)"}
    run:
      - {step: seed, kind: script, cmd: "python3 -I scripts/seed_repo.py --from {seed} --target {target}", skip_if_missing: [seed]}
      - {step: install, kind: script, cmd: "python3 -I scripts/install_ci.py --target {target} [--deploy {deploy}] --report-json {out}/ci-report.json --report-md {out}/ci-report.md"}
    outputs:
      - {path: "{out}/ci-report.json", checks: [exists, json, contains:"jobs_found", contains:"deploy_workflows", contains:"flavour"]}
      - {path: "{out}/ci-report.md", checks: [exists, sections:["Read before write","Workflows","Standard jobs","Branch protection","Next steps"]]}
      - {path: "{target}/.github/workflows/ci.yml", checks: [exists, yaml]}
    modes:
      new: {case: agent-happy-path, bring: "an empty or brand-new repo folder"}
      existing: {case: agent-mode-existing, bring: "your repo with its current workflows and package.json (a repo that already deploys to AWS/Azure/GCP keeps its deploy workflows and gets only the CI-only pieces — case agent-mode-existing-aws)"}
---

# ci-cd-vercel-github

## In a conversation: design the pipeline now
- **The request names the goal** (new pipeline, add a stage, tag-based prod releases): answer **in this reply** with, in order: (1) the stage table — stage → trigger → job → required check name (`ci / lint-typecheck-test`, `ci / rls-lint`, `preview / e2e`) → secrets → timeout — and a line that no file is written until you reply "go"; (2) the three workflows `.github/workflows/ci.yml`, `preview.yml`, `prod.yml` with their jobs, and every `npm run <script>` they call listed for checking against `package.json`; (3) the env/secret matrix — each secret → GitHub secret, Vercel env or GitHub Environment (`staging`, `production`) — names only, never values, with the `gh secret set` commands; (4) the prod path in `prod.yml`: tag on `main` verified by `git merge-base`, migrate staging → migrate prod behind the `production` Environment reviewer gate, deploy, smoke `/api/health` and `/api/health/deep`, release; (5) the rollback runbook installed at `docs/runbooks/rollback.md` (Vercel Instant Rollback plus the migration revert path); (6) the branch-protection commands. Repo facts not in the request (project refs, existing scripts) are `[TO BE BASELINED — owner: ___]`, asked at the end. Never reply with only a request for the workflow files.
- **A run failed and the log line is given**: name the cause from the log, give the minimal fix, and say which steps stay untouched. For `supabase db push` "migration … applied with different checksum": an already-applied migration file was edited; restore the original file from git history and move the change into a new, later-numbered migration — never `supabase migration repair`, never delete or rewrite migration history to make the run pass. Change no unrelated workflow step.
- **"Deploy to production" with no environment facts**: ask once, in one list, for the Vercel project, the Supabase project refs for staging and prod, and whether the GitHub Environments `staging`/`production` exist. Do not deploy, tag or promote anything until they arrive and you say "go".
- **Asked to drop a required check or mark CI done while a stage is missing**: decline in one line (branch protection depends on those check names), list what is missing, and offer the merge from `assets/workflows/`.

## Starting points
- **New** — point `target` at an empty folder: all three workflows are written from `assets/workflows/` and validated.
- **Existing** — point `target` at your repo: customised workflows are kept and validated job by job, missing ones are added, and every `npm run` they call is checked against your package.json. A kept `ci.yml` that lacks standard jobs never fails the run: the missing jobs are proposed in `.github/ci-additions.yml` (outside `workflows/`, so Actions ignores it) for you to merge by hand, and the report lists every standard job as present/missing.
- **Existing, deploys elsewhere** — the script reads the workflows first. AWS (`aws-actions/`, `amazon-ecr`, ECS/CDK/SAM), Azure, Google Cloud, Fly.io or Railway detected and no real Vercel signal (a linked `.vercel/project.json`, `vercel deploy`, `VERCEL_TOKEN`; a bare `vercel.json` or a `*.vercel.app` hostname does not count): `preview.yml`/`prod.yml` are **not** written, the report names the detected target, and only `ci.yml` + its check names are offered. Pass `--input deploy=vercel` to force the Vercel workflows, `deploy=skip` to never write them.

## Read before write (every run)
| Read | Decides |
|---|---|
| `tsconfig.json` / `.ts` sources, else `jsconfig.json` / `.js` sources | language flavour — a JavaScript repo gets the secrets-scan grep widened to `*.js`/`*.jsx`; `npm run typecheck` is flagged when the script is absent |
| `.github/workflows/*.yml` (comments stripped), `package.json` scripts, `vercel.json`, `.vercel/project.json` | deploy target — Vercel workflows only when Vercel is the target (or the repo has no deploy yet) |
| existing `ci.yml`/`ci.yaml`, `preview.*`, `prod.*` | kept, never overwritten; never a `.yml` beside a `.yaml` sibling; missing standard jobs → `<name>-additions.yml` |
| existing `<name>-additions.yml` | identical → kept; different → **conflict**: nothing is written, exit 1 |

All writes are atomic: everything is computed first and written only when no conflict (malformed kept workflow, clashing additions file) exists; otherwise nothing lands in the repo and `ci-report.md` says why.

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

Missing repo facts do not stop the design: mark them `[TO BE BASELINED — owner: ___]` and ask at the end. Only when the goal is absent, or prod work is asked without the Vercel and Supabase project refs, ask once and do not deploy or tag.

## Procedure
1. Read `../../../shared/stack-conventions.md` (CI row), `../../../shared/token-efficiency.md`. Read existing workflows and `package.json` scripts; map what runs where today.
2. **Plan.** Stage table (from `references/pipeline-stages.md`): stage → trigger → job → required check name → secrets. For fixes: failing step → root cause hypothesis → minimal change. Post; wait for "go". *(gate: plan→approve)*
3. **Build.** Read the repo first (flavour, deploy target, existing workflows — table above). Copy/merge `assets/workflows/ci.yml`, and `preview.yml`/`prod.yml` only when Vercel is the deploy target; never overwrite a customised workflow — diff and merge, or hand the team `ci-additions.yml`. Confirm every `npm run <script>` exists. Fill the env/secret matrix from `references/env-promotion.md`; list `gh secret set` commands (values never in chat).
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
- `scripts/install_ci.py` — read-before-write installer: detects flavour and deploy target, writes absent workflows (Vercel deploy workflows only for Vercel targets), keeps existing ones, proposes missing standard jobs as `<name>-additions.yml`, validates `on:`/`jobs:`; atomic, exit 1 only on conflict

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs above, then run `python3 scripts/run_skill.py build/ci-cd-vercel-github --input <name>=<value> … --out <dir>` (see `--explain build/ci-cd-vercel-github`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. A kept (customised) workflow that lacks a standard job gives `gate: NEEDS-MERGE` (exit 0) and `.github/<name>-additions.yml` to merge by hand — branch protection depends on those check names, so do not call CI done until the Standard-jobs table is all `present`. A repo that deploys to AWS/Azure/GCP/Fly.io/Railway gets no Vercel deploy workflows unless `--input deploy=vercel` is passed; the report names the detected target. Exit 1 means nothing was written: a kept workflow is malformed or an additions file clashes.
