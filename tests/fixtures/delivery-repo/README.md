FICTIONAL fixture repo for the delivery-pipeline tests (Harborline Portal is invented; not a real project).
A JavaScript Next.js 14 app (jsconfig.json, no tsconfig) with vitest + Playwright declared, deploying to AWS ECS
through `.github/workflows/aws-deploy-production.yml`, with its own `ci.yml`. No Vercel link, no migrations dir.
Expected stack profile: flavour js, framework nextjs, package_manager npm, test_runner vitest, e2e playwright,
deploy_target aws, migrations_dir null, monorepo_root null, baselines all null.
