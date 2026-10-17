---
name: observability-setup
description: Use when an app is going to production or lacks visibility — "add logging", "set up Sentry", "health checks", "alerts", "we can't see what's failing". Produces structured JSON logging (lib/logger.ts), error tracking wiring, /api/health and /api/health/deep endpoints, alert rules, an SLO starter and a minimal dashboard spec for the Next.js + Supabase + Vercel stack. Not for debugging a specific failure (use safe-fix) or CI (use ci-cd-vercel-github).
license: MIT
metadata:
  domain: build
  version: 0.1.0
  author: giri-skills
---

# observability-setup

## When to use
- First production release; after an incident with "we had no idea"; before an SLA commitment.
- Adding a new service/edge function/job that has no logs or health signal.
- NOT for: a specific bug (`safe-fix`), pipeline alerts (`ci-cd-vercel-github`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Critical user journeys (≤5) | yes | `docs/SPEC.md` / user — ask once |
| Error-tracking vendor decision (Sentry default) and DSN availability | yes | user |
| Log sink (Vercel Log Drain target) | no | user; default: vendor's drain |
| On-call / notification channel | yes | user — ask once |
| Existing `lib/logger.ts`, health routes | yes | repo |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../../shared/stack-conventions.md` (Logging, Errors rows) and `../../../shared/token-efficiency.md`. Inventory what exists: logger, Sentry, health routes, Vercel integrations.
2. **Plan.** Table of components to add/change: logger, request context, error tracking (server + client + edge), health endpoints, alert rules, SLOs, dashboard, runbook links. Post; wait for "go". *(gate: plan→approve)*
3. **Logging.** Install `assets/logger.ts` as `lib/logger.ts` (+ `lib/logger/context.ts` AsyncLocalStorage) per `references/log-schema.md`; wire `requestId` in `middleware.ts`; ESLint `no-console: error`. Replace existing `console.*` in minimal diffs.
4. **Error tracking.** Follow `references/error-tracking.md`: server, client, edge configs; `requestId`/`tenantId` tags; PII scrubbing; source maps in CI; `error.tsx` reporting.
5. **Health.** Add `assets/health-route.ts` as `app/api/health/route.ts` (liveness, no deps) and `app/api/health/deep/route.ts` (DB, auth, storage, queue; bearer-protected) per `references/health-endpoints.md`.
6. **Alerts + SLOs.** From `references/alerts-and-slos.md`, fill `assets/alert-rules.yaml` for the chosen vendor and the SLO table for the critical journeys. Every alert has a runbook link and an owner.
7. **Test.** Unit test logger redaction; integration test both health routes (200 / 503 on simulated DB failure); trigger a test error and confirm it appears in the tracker with `requestId`. Full unit suite green. *(gate: build→test)*
8. **Verify.** Deploy to preview; curl both health routes; confirm Log Drain delivers JSON; confirm an alert fires on a synthetic failure (health 503). *(gate: test→verify)*
9. Write `docs/observability.md` (schema, endpoints, alerts, dashboards, how to find a request by id). Update `docs/HANDOFF.md`.

## Output
| Artifact | Path |
|---|---|
| Logger | `lib/logger.ts`, `lib/logger/context.ts` |
| Error tracking | `sentry.{server,client,edge}.config.ts` (or vendor equivalent), `app/global-error.tsx` |
| Health | `app/api/health/route.ts`, `app/api/health/deep/route.ts` |
| Alerts / SLOs | `ops/alerts.yaml`, `docs/observability.md` |
| Dashboard spec | `docs/observability.md` §Dashboards |

## Self-check
- [ ] Every log line has `ts, level, msg, service, env`; request-scoped lines have `requestId`
- [ ] Redaction list covers email, token, password, authorization, cookie, key
- [ ] Health liveness has zero dependencies; deep check is auth-protected and times out ≤ 3 s per dependency
- [ ] Every alert: threshold, window, severity, runbook, owner, notification channel
- [ ] SLOs defined for each critical journey with an error-budget policy
- [ ] Synthetic failure produced an alert end-to-end
- [ ] No PII reached the error tracker (checked a real event)

## References
- `references/log-schema.md` — fields, levels, redaction, request context
- `references/error-tracking.md` — Sentry (default) wiring for server/client/edge, scrubbing, source maps
- `references/health-endpoints.md` — liveness vs readiness vs deep; response contract
- `references/alerts-and-slos.md` — alert catalogue, SLO starter, error-budget policy, dashboard panels
- `assets/logger.ts`, `assets/logger-context.ts`, `assets/health-route.ts`, `assets/health-deep-route.ts`, `assets/alert-rules.yaml`
