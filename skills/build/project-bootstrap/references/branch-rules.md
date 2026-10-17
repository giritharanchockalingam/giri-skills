# Branch, PR and Release Rules

## Branch model
| Branch | Purpose | Deploys to | Protected |
|---|---|---|---|
| `main` | Always releasable | Preview (auto) → Production (tag only) | yes |
| `feat/<ticket>-<slug>` | One feature or task | Vercel preview per PR | no |
| `fix/<ticket>-<slug>` | One bug | Vercel preview per PR | no |
| `chore/<slug>` | Deps, CI, docs | preview | no |
| `hotfix/<slug>` | Prod fix branched from the prod tag | preview → tag | no |

No long-lived `develop`/`staging` branches. Staging = the preview deployment of `main`.

## Naming
- Commits: Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`). Scope optional: `feat(auth): …`.
- Tags: `v<major>.<minor>.<patch>` on `main` only. Tag = prod release.
- PR title = squash commit message.

## PR rules
| Rule | Enforced by |
|---|---|
| Squash merge only; linear history | branch protection |
| ≥1 approving review; CODEOWNERS review for `supabase/`, `server/`, `.github/` | branch protection + CODEOWNERS |
| Required checks green: `ci`, `preview / e2e` | branch protection |
| PR template checklist completed (tests, migration rollback, env vars, HANDOFF) | review |
| No PR > ~400 changed lines without a stated reason | review |
| Migrations never edited after merge; new migration instead | review + `rls_lint.py` |

## `gh` commands (run after approval; replace `<owner>/<repo>`)
```bash
# Protect main: PR required, 1 review, code-owner review, required checks, linear history, no force-push
gh api -X PUT repos/<owner>/<repo>/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  --input - <<'JSON'
{
  "required_status_checks": {"strict": true, "contexts": ["ci / lint-typecheck-test", "preview / e2e"]},
  "enforce_admins": true,
  "required_pull_request_reviews": {"required_approving_review_count": 1, "require_code_owner_reviews": true, "dismiss_stale_reviews": true},
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON

# Squash-only merges
gh api -X PATCH repos/<owner>/<repo> -f allow_merge_commit=false -f allow_rebase_merge=false -f allow_squash_merge=true -f delete_branch_on_merge=true

# Secret scanning + push protection
gh api -X PATCH repos/<owner>/<repo> --input - <<'JSON'
{"security_and_analysis": {"secret_scanning": {"status": "enabled"}, "secret_scanning_push_protection": {"status": "enabled"}}}
JSON

# Required secrets (values from Vercel / Supabase dashboards; never paste into chat)
gh secret set VERCEL_TOKEN
gh secret set VERCEL_ORG_ID
gh secret set VERCEL_PROJECT_ID
gh secret set SUPABASE_ACCESS_TOKEN
gh secret set SUPABASE_DB_PASSWORD
gh secret set SUPABASE_PROJECT_REF_STAGING
gh secret set SUPABASE_PROJECT_REF_PROD
```

## Release flow
1. Merge PRs to `main` → preview deploy of `main` is staging.
2. Verify staging (smoke e2e in `preview.yml` already ran).
3. `git tag v1.4.0 && git push origin v1.4.0` → `prod.yml` runs migrations then deploys.
4. Rollback: see `ci-cd-vercel-github/references/rollback.md`.
