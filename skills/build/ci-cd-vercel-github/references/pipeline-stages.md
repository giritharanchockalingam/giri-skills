# Pipeline Stages

## Overview
```
PR opened/updated ──► ci.yml ───────────────► preview.yml ──────────────► merge to main
                      lint → typecheck →       vercel preview → e2e           │
                      unit+coverage → build    (+ preview URL comment)        ▼
                      rls-lint, secrets-scan                           preview of main = staging
                                                                               │  tag vX.Y.Z
                                                                               ▼
                                        prod.yml: verify-tag → migrate-staging → [gate] migrate-prod → deploy-prod → smoke → release
```

## Stage table
| Stage | Workflow / job | Trigger | Required check name | Timeout | Fails when |
|---|---|---|---|---|---|
| Lint + typecheck + unit + build | `ci.yml` / `lint-typecheck-test` | PR, push main | `ci / lint-typecheck-test` | 15 min | eslint error, tsc error, test fail, coverage < 80% on server/, build error |
| RLS lint | `ci.yml` / `rls-lint` | PR, push main | `ci / rls-lint` | 5 min | any RLS error finding |
| Secrets scan | `ci.yml` / `secrets-scan` | PR, push main | `ci / secrets-scan` | 5 min | `.env*` committed; `NEXT_PUBLIC_*SERVICE_ROLE*` |
| Preview deploy | `preview.yml` / `deploy-preview` | PR | — | 20 min | vercel build/deploy error |
| E2E | `preview.yml` / `e2e` | after preview | `preview / e2e` | 30 min | playwright failure after 2 retries |
| Verify tag | `prod.yml` / `verify-tag` | tag `v*.*.*` | — | 2 min | tag commit not on main |
| Migrate staging | `prod.yml` / `migrate-staging` | after verify | — | 15 min | `supabase db push` error |
| Migrate prod | `prod.yml` / `migrate-prod` | after staging; **production** Environment approval | — | 15 min | push error |
| Deploy prod | `prod.yml` / `deploy-prod` | after migrate | — | 20 min | build/deploy error |
| Smoke | `prod.yml` / `deploy-prod` step | after deploy | — | 2 min | `/api/health` or `/api/health/deep` not ok |
| Release | `prod.yml` / `deploy-prod` step | after smoke | — | 1 min | — |

## Conventions
| Topic | Rule |
|---|---|
| Check names | `<workflow name> / <job id>`; these exact strings go into branch protection |
| Concurrency | `ci-${{ github.ref }}` and `preview-${{ github.ref }}` cancel in progress; `prod` group never cancels |
| Permissions | `permissions:` block per workflow; least privilege (`contents: read` default) |
| Node | `actions/setup-node@v4` with `cache: npm`; version pinned via `NODE_VERSION` env (match `.nvmrc`) |
| Caching | npm cache via setup-node; Next build cache: `actions/cache` on `.next/cache` keyed by lockfile + source hash (optional) |
| Artifacts | coverage (7 days), playwright report on failure (7 days) |
| Timeouts | every job has `timeout-minutes` |
| Secrets in logs | never `echo $SECRET`; derived values masked with `echo "::add-mask::$VAL"` |
| Fork PRs | secrets unavailable → `preview.yml` skips deploy for forks (`if: github.event.pull_request.head.repo.full_name == github.repository`) |
| Integration tests in CI | optional job `integration` with `supabase/setup-cli` + `supabase start`; add when `tests/integration` exists (adds ~3 min) |

## Adding a stage (procedure)
1. Add the job to the right workflow with `needs:` wiring and `timeout-minutes`.
2. Make it required in branch protection only after it has passed on 3 PRs.
3. Document in `docs/ci-cd.md`.

## Optional integration job (`ci.yml`)
```yaml
  integration:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: npm }
      - uses: supabase/setup-cli@v1
        with: { version: latest }
      - run: supabase start
      - run: npm ci
      - name: Export local keys
        run: |
          supabase status -o env >> "$GITHUB_ENV"
      - run: npm test -- --project integration
```
