# Troubleshooting CI/CD

| Symptom | Likely cause | Fix |
|---|---|---|
| `ci` passes locally, fails in CI on typecheck | CI uses `npm ci` with lockfile; local has newer deps | run `npm ci` locally; commit lockfile |
| Coverage gate fails right after adding tests | `coverage-summary.json` not generated (`json-summary` reporter missing) | add reporter in `vitest.config.ts` |
| `vercel pull` fails: "project not found" | `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` wrong or token scope | `vercel link` locally, copy ids from `.vercel/project.json` |
| Preview URL 401 in Playwright | protection bypass header missing | set `VERCEL_AUTOMATION_BYPASS_SECRET`; `extraHTTPHeaders` in config |
| E2E flaky only in CI | timing; shared test data | web-first assertions; unique data per worker; 2 retries |
| `supabase db push` "migration already applied with different checksum" | an applied migration was edited | revert the edit; add a new migration |
| `supabase link` asks for password interactively | `SUPABASE_DB_PASSWORD` not exported | set env in the step |
| Prod job skipped | tag not on `main` or Environment approval pending | check `verify-tag` logs; approve in Actions UI |
| Two preview deployments per PR | Vercel git integration AND `preview.yml` both deploying | disable one (see env-promotion.md) |
| Secrets empty on fork PR | GitHub does not pass secrets to forks | gate deploy job on same-repo condition |
| Build fails: env var missing | `lib/env.ts` zod parse at build | add placeholder in `ci.yml` build step env, real value in Vercel |
| Playwright browsers not installed | cache restored without browsers | `npx playwright install --with-deps chromium` every run |
| Smoke fails `/api/health/deep` 401 | `HEALTH_CHECK_TOKEN` differs between Vercel and GitHub | align secrets |
