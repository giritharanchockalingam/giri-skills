# Alerts, SLOs, Dashboards

## Alert principles
| Principle | Practice |
|---|---|
| Alert on symptoms users feel, not causes | error rate, latency, health, job lag — not CPU |
| Every alert pages or notifies a human who can act, and links a runbook | `runbook:` field mandatory |
| Two tiers | **page** (wake someone) vs **notify** (channel, next business hour) |
| Windows beat thresholds | 5-min rolling windows; require 2 consecutive breaches for page |
| Test every alert on preview before trusting it in prod | `?simulate=` on deep health |

## Alert catalogue (starter — see `assets/alert-rules.yaml`)
| ID | Signal | Condition | Tier | Runbook |
|---|---|---|---|---|
| A1 | `/api/health` | 2 consecutive failures (1-min probe) | page | `runbooks/app-down.md` |
| A2 | `/api/health/deep` | status `down` for 2 probes (5-min) | page | `runbooks/dependency-down.md` |
| A3 | 5xx rate (Vercel) | > 2% of requests over 5 min AND > 20 requests | page | `runbooks/error-spike.md` |
| A4 | p95 latency (Vercel) | > 1500 ms over 10 min on `(app)` routes | notify | `runbooks/latency.md` |
| A5 | Error tracker | new issue in prod | notify | triage |
| A6 | Error tracker | same issue > 10 events / 5 min | page | `runbooks/error-spike.md` |
| A7 | Logs | `level=error` count > 10 / 5 min | notify | search by `requestId` |
| A8 | Jobs | pending older than 15 min > 0 | notify | `runbooks/jobs-stuck.md` |
| A9 | Supabase | DB CPU > 80% 10 min, or disk > 85%, or connections > 80% pool | notify | `runbooks/db-capacity.md` |
| A10 | Auth | sign-in failure rate > 30% over 15 min AND > 50 attempts | notify | `runbooks/auth-failures.md` |
| A11 | Deploy | `prod.yml` failed or smoke failed | notify | `ci-cd-vercel-github/references/rollback.md` |
| A12 | Budget | Vercel/Supabase spend > 80% of monthly cap | notify | finance owner |

## SLO starter (per critical journey; fill from SPEC)
| Journey | SLI | SLO (30-day) | Error budget | Measure |
|---|---|---|---|---|
| Sign-in | successful sign-ins / attempts (excl. bad password) | 99.5% | 0.5% | logs `action=auth.signin outcome` |
| Primary create flow | 2xx / all server-action calls for `<domain>.create` | 99.5% | 0.5% | logs `action outcome` |
| Page load (app) | requests with p95 < 1 s | 95% | 5% | Vercel Speed Insights / logs `durationMs` |
| API (external) | non-5xx / all | 99.9% | 0.1% | Vercel |
| Availability | health probes ok / all | 99.9% | ~43 min/month | uptime monitor |

### Error-budget policy
| Budget remaining | Action |
|---|---|
| > 50% | normal release cadence |
| 20–50% | releases need an explicit rollback plan and reviewer sign-off |
| < 20% | feature freeze on that journey; reliability work only until budget recovers |
| exhausted | incident review required; postmortem before next release |

## Dashboard (one page, four rows)
| Row | Panels |
|---|---|
| 1 Health | deep-health status per dependency; uptime 30d; current deploy sha |
| 2 Traffic & errors | requests/min; 5xx rate; top error codes (`outcome`) by count |
| 3 Latency | p50/p95/p99 by route group; slowest 5 routes |
| 4 Business/async | sign-ins/hr; primary creates/hr; job queue depth + oldest pending; SLO burn rate |

Build in the log sink / Vercel Observability; keep queries in `docs/observability.md` so they are reproducible.

## Runbook template (`runbooks/<name>.md`)
```
# <Alert name>
Symptom: …          Severity: page/notify
First 5 minutes: 1) check deep health 2) check last deploy (rollback?) 3) check Supabase status 4) search logs level=error last 15m
Likely causes → fixes: …
Escalate to: <owner>      Rollback: ci-cd-vercel-github/references/rollback.md
```
