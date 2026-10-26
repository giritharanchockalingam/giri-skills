FICTIONAL example repo for evals (Harborline Portal is invented). A JavaScript Next.js 14 app (JSX, `route.js`,
jsconfig.json, no tsconfig) that already deploys to AWS ECS through `aws-deploy-uat.yml` / `aws-deploy-production.yml`
and has its own `ci.yml` (verify + docker jobs, no rls-lint / secrets-scan). `vercel.json` holds only a region and there
is no `.vercel/project.json` link and no VERCEL_* secret anywhere: Vercel is not the deploy target.
Expected: preview.yml and prod.yml are NOT written, ci.yml is kept, the missing jobs land in `.github/ci-additions.yml`, exit 0.
