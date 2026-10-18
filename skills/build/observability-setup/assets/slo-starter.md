# Observability — {{PROJECT}}

Installed by `observability-setup/scripts/install.py`. Fill the journeys from `docs/SPEC.md`; see
`references/alerts-and-slos.md` for the alert catalogue and dashboard rows.

## Log schema
`ts, level, msg, service, env, version` on every line; `requestId` (and `userId`, `tenantId` when known) on request-scoped
lines. Find a request: search logs for `requestId=<id>`. Redacted keys: email, token, password, authorization, cookie, key.

## Endpoints
| Endpoint | Purpose | Auth | Timeout |
|---|---|---|---|
| `GET /api/health` | liveness — no dependencies | none | — |
| `GET /api/health/deep` | readiness — DB, auth, storage, queue | `Authorization: Bearer $HEALTH_CHECK_TOKEN` | ≤ 3 s per dependency |

## SLOs (per critical journey; 30-day window)
| Journey | SLI | SLO | Error budget | Measure | Owner |
|---|---|---|---|---|---|
| Sign-in | successful sign-ins / attempts (excl. bad password) | 99.5% | 0.5% | logs `action=auth.signin outcome` | [TO BE BASELINED — owner: ___] |
| Primary create flow | 2xx / all server-action calls for `<domain>.create` | 99.5% | 0.5% | logs `action outcome` | [TO BE BASELINED — owner: ___] |
| Page load (app) | requests with p95 < 1 s | 95% | 5% | Vercel Speed Insights / logs `durationMs` | [TO BE BASELINED — owner: ___] |
| API (external) | non-5xx / all | 99.9% | 0.1% | Vercel | [TO BE BASELINED — owner: ___] |
| Availability | health probes ok / all | 99.9% | ~43 min/month | uptime monitor | [TO BE BASELINED — owner: ___] |

### Error-budget policy
| Budget remaining | Action |
|---|---|
| > 50% | normal release cadence |
| 20–50% | releases need an explicit rollback plan and reviewer sign-off |
| < 20% | feature freeze on that journey; reliability work only until budget recovers |
| exhausted | incident review required; postmortem before next release |

## Alerts
Defined in `ops/alerts.yaml` (vendor-neutral). Every rule needs a runbook link and an owner before go-live.

## Dashboards
| Row | Panels |
|---|---|
| 1 Health | deep-health status per dependency; uptime 30d; current deploy sha |
| 2 Traffic & errors | requests/min; 5xx rate; top error codes (`outcome`) by count |
| 3 Latency | p50/p95/p99 by route group; slowest 5 routes |
| 4 Business/async | sign-ins/hr; primary creates/hr; job queue depth + oldest pending; SLO burn rate |
