# Health Endpoints

| Endpoint | Purpose | Auth | Dependencies | Used by |
|---|---|---|---|---|
| `GET /api/health` | liveness: process up, build info | none | none | uptime monitor (every 1 min), prod smoke in `prod.yml` |
| `GET /api/health/deep` | readiness: each dependency checked with timeout | `Authorization: Bearer ${HEALTH_CHECK_TOKEN}` | DB, auth, storage, queue, critical external | synthetic monitor (every 5 min), post-deploy smoke, on-call |

## Response contract
```json
{
  "status": "ok" | "degraded" | "down",
  "version": "<git sha>",
  "env": "production",
  "ts": "2026-01-01T00:00:00.000Z",
  "checks": {
    "db":      { "status": "ok", "latencyMs": 12 },
    "auth":    { "status": "ok", "latencyMs": 40 },
    "storage": { "status": "degraded", "latencyMs": 2900, "detail": "slow" },
    "queue":   { "status": "down", "error": "timeout" }
  }
}
```
HTTP: `200` for `ok`/`degraded`, `503` for `down`. `degraded` = any check slow (> `slowMs`) or an optional dependency down; `down` = any required dependency failed.

## Rules
| Rule | Why |
|---|---|
| Liveness never touches a dependency | a DB outage must not make the app "dead" to the platform |
| Deep check per-dependency timeout ≤ 3 s, total ≤ 8 s | monitors time out at 10 s |
| Deep check protected | it reveals topology and can be used to load the DB |
| `Cache-Control: no-store`, `export const dynamic = 'force-dynamic'`, `runtime = 'nodejs'` | never cached; service role needs node |
| DB check = `select 1` via service role **or** a trivial RLS-safe read; never a heavy query | cost |
| Checks read-only | never write from health |
| `?simulate=error|slow` honoured only when `VERCEL_ENV !== 'production'` | lets alerts be tested on preview |
| Every check logs at `warn` on degraded, `error` on down with `requestId` | correlates with alerts |

## Which dependencies are "required"
| Dependency | Required | Check |
|---|---|---|
| Postgres | yes | `select 1` |
| Supabase Auth | yes | `GET ${SUPABASE_URL}/auth/v1/health` |
| Storage | if uploads are core | `storage.listBuckets()` limit 1 |
| Queue / jobs table | if async flows are core | `select count(*) from jobs where status='pending' and created_at < now() - interval '15 min'` → degraded if > 0 |
| Payment provider | optional | `GET /v1/balance` style lightweight call (cached 60 s) |
