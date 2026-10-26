# repo-js-existing-health (fixture)

A JavaScript Next.js 14 app (no tsconfig.json, JSX in .js files) that deploys to AWS via GitHub Actions
and already has its own `app/api/health/route.js` (which probes Supabase — a liveness-vs-deep gap) but no
logger. The brownfield shape that produced the route.js/route.ts conflict. Evals copy it with
`scripts/seed_repo.py` before running the install; the fixture itself is never written to.
