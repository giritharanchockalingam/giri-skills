# Environments, Secrets, Promotion

## Environment matrix
| Environment | Code | Vercel env | Supabase project | DB data | Who can reach |
|---|---|---|---|---|---|
| Local | working tree | — | local (`supabase start`) | seed | developer |
| Preview (PR) | PR branch | Preview | **staging** project (shared) or branch DB (Supabase Branching) | seed / synthetic | team (Vercel Authentication on) |
| Staging | `main` | Preview (of main) | staging | synthetic, prod-shaped | team |
| Production | tag `vX.Y.Z` | Production | prod | real | public |

Rules: preview never points at prod DB; staging DB is reset from seed weekly or uses branching; prod env vars marked **Sensitive** in Vercel.

## Variables and secrets
| Name | Where | Scope | Notes |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_APP_URL` | Vercel env | Dev / Preview / Prod, per-environment values | public |
| `SUPABASE_SERVICE_ROLE_KEY` | Vercel env (Sensitive) | Preview / Prod | server only |
| `HEALTH_CHECK_TOKEN`, `SENTRY_DSN`, `LOG_LEVEL` | Vercel env | Preview / Prod | |
| `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` | GitHub secrets | repo | deploy from Actions |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | GitHub secret | repo | Playwright through preview protection |
| `SUPABASE_ACCESS_TOKEN` | GitHub secret | repo | CLI auth |
| `SUPABASE_PROJECT_REF_STAGING`, `SUPABASE_DB_PASSWORD_STAGING` | GitHub Environment `staging` | | |
| `SUPABASE_PROJECT_REF_PROD`, `SUPABASE_DB_PASSWORD_PROD` | GitHub Environment `production` | | required reviewers on this Environment |
| `E2E_USER_EMAIL/PASSWORD`, `E2E_VIEWER_EMAIL/PASSWORD` | GitHub secrets | repo | seeded staging accounts |
| `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` | GitHub secrets | repo | source maps |

Set with `gh secret set NAME` (prompts for value) or `gh secret set NAME --env production`.

## Vercel project settings
| Setting | Value |
|---|---|
| Git integration | connected, but **Production Branch deploys disabled** ("Ignored Build Step" returns 1 for `main`, or disconnect prod auto-deploy) — prod ships only via `prod.yml` |
| Preview deployments | enabled for PR branches (Vercel's own) *or* via `preview.yml` — pick one to avoid double builds; the template uses Actions for control |
| Deployment protection | Vercel Authentication on Preview; Protection Bypass for Automation enabled |
| Environment variables | per environment as above; "Sensitive" for secrets |
| Functions region | same region as Supabase project |
| Instant Rollback | on (Pro) |

## Promotion flow
| Step | Actor | Command / action | Gate |
|---|---|---|---|
| 1 | dev | open PR | `ci`, `preview / e2e` green; review |
| 2 | reviewer | squash-merge to `main` | — |
| 3 | auto | preview of `main` = staging | smoke via e2e already ran on PR |
| 4 | release owner | `git tag v1.4.0 && git push origin v1.4.0` | tag on main |
| 5 | auto | migrate staging | success |
| 6 | reviewer | approve **production** Environment in GitHub | human gate |
| 7 | auto | migrate prod → deploy → smoke → GitHub Release | health ok |
| 8 | release owner | watch alerts 30 min; update HANDOFF | — |

## Versioning
Semver tags. `patch` = fixes, `minor` = features, `major` = breaking API/schema contract. Hotfix: branch from the tag, PR to main, tag `v1.4.1`.
