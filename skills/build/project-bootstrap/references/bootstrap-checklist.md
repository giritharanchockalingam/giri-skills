# Bootstrap Checklist (Next.js + Supabase + Vercel)

Every row ends Done, Skipped (reason), or `[TO BE BASELINED — owner: ___]`.

## A. Repo docs (scaffold writes these)
| # | File | Purpose | Done |
|---|---|---|---|
| A1 | `docs/SPEC.md` | What we are building; scope; NFRs; tenancy | |
| A2 | `CLAUDE.md` | How we work in this repo: commands, conventions, gates | |
| A3 | `docs/HANDOFF.md` | Where we are; next-thread prompt | |
| A4 | `docs/adr/0000-template.md` | ADR template | |
| A5 | `docs/adr/0001-stack.md` | Stack decision + deviations | |
| A6 | `.env.example` | Env contract — every var documented, no values | |
| A7 | `.github/workflows/ci.yml` | lint → typecheck → unit → build on PR | |
| A8 | `.github/workflows/preview.yml` | Vercel preview + e2e on PR | |
| A9 | `.github/workflows/prod.yml` | Tag-triggered prod deploy with migrations | |
| A10 | `.github/CODEOWNERS` | Review ownership | |
| A11 | `.github/pull_request_template.md` | PR checklist with gates | |

## B. App skeleton (scaffold writes the minimal runnable app when no package.json exists)
| # | Item | Command / note | Done |
|---|---|---|---|
| B1 | Minimal Next.js app (App Router, `@/*` alias, ESLint, vitest) | written by `scaffold.py --stack nextjs-js\|nextjs-ts`: `package.json`, `next.config.js` (security headers), `jsconfig.json`/`tsconfig.json`, `.eslintrc.json`, `vitest.config.*`, `app/layout`, `app/page`, `app/api/health/route`, `lib/app-info`, `tests/unit/health.test`, `.gitignore`. A repo with a package.json keeps its app untouched. | |
| B2 | Lockfile committed | `npm install` once locally, commit `package-lock.json` — `ci.yml` runs `npm ci` only with it (until then it warns and runs `npm install`) | |
| B3 | Folder layout per `shared/stack-conventions.md` | `mkdir -p components/ui components/features lib/supabase lib/db lib/utils server/actions server/services server/validators supabase/migrations tests/e2e tests/fixtures` | |
| B4 | `env.ts` zod parser at boot | `lib/env.ts`; import in `next.config.js` to fail fast | |
| B5 | Supabase clients | `lib/supabase/server.ts` (cookies), `lib/supabase/browser.ts` (anon only) — feature work, not bootstrap | |
| B6 | Logger | copy `observability-setup/assets/logger.ts` → `lib/logger.ts` | |
| B7 | Result type | `lib/result.ts` — see `nextjs-enterprise-conventions/references/error-result-pattern.md` | |
| B8 | Playwright | copy the e2e config from `test-strategy-tdd/assets/` (vitest is already configured) | |
| B9 | `package.json` scripts beyond the skeleton | `test:e2e, db:migrate, db:reset, db:types` (`dev, build, start, lint, typecheck, test` are written) | |
| B10 | Tailwind / UI kit | only if the first feature needs it (`shadcn` vendor skill) | |

## C. Supabase
| # | Item | Note | Done |
|---|---|---|---|
| C1 | `supabase init` + `supabase start` locally | local stack before any remote | |
| C2 | Project per environment: dev (local), staging, prod | never share prod DB with preview | |
| C3 | First migration: `0001_init.sql` with tenancy tables + RLS enabled | use `supabase-schema-rls` | |
| C4 | `supabase gen types typescript --local > lib/db/types.ts` wired to `db:types` | | |
| C5 | Service-role key stored only in Vercel server env | never `NEXT_PUBLIC_` | |

## D. Vercel
| # | Item | Note | Done |
|---|---|---|---|
| D1 | Project linked to GitHub repo | `vercel link` | |
| D2 | Env vars per environment (Development / Preview / Production) | match `.env.example` exactly | |
| D3 | Production branch = `main`; prod deploys only from tag workflow | disable auto-prod on push | |
| D4 | Preview protection (Vercel Authentication) on | | |
| D5 | `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` as GitHub secrets | | |

## E. GitHub
| # | Item | Note | Done |
|---|---|---|---|
| E1 | Branch protection on `main` | see `branch-rules.md` | |
| E2 | Required checks: `ci / lint-typecheck-test`, `preview / e2e` | | |
| E3 | Secrets: Vercel trio, `SUPABASE_ACCESS_TOKEN`, `SUPABASE_DB_PASSWORD`, `SUPABASE_PROJECT_REF_STAGING/PROD` | | |
| E4 | Dependabot or Renovate enabled (weekly, grouped) | | |
| E5 | Secret scanning + push protection on | | |

## F. Definition of "bootstrapped"
- `npm run lint && npm run typecheck && npm test && npm run build` passes locally.
- Opening a PR triggers `ci.yml` and `preview.yml`; both green.
- `docs/HANDOFF.md` contains the next-thread prompt for the first feature.
