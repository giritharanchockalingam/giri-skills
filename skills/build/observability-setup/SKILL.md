---
name: observability-setup
description: Use when an app is going to production or lacks visibility — "add logging", "set up Sentry", "health checks", "alerts", "we can't see what's failing". Produces structured JSON logging (lib/logger.ts), error tracking wiring, /api/health and /api/health/deep endpoints, alert rules, an SLO starter and a minimal dashboard spec for the Next.js + Supabase + Vercel stack. Not for debugging a specific failure (use safe-fix) or CI (use ci-cd-vercel-github).
license: MIT
metadata:
  domain: build
  adlc_stage: operate
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: target, type: path, required: true, from: "Next.js repo root (created if absent)"}
      - {name: project, type: string, required: false, from: "project name for docs/observability.md (default: target dir name)"}
      - {name: dry_run, type: flag, required: false, flag: "--dry-run", from: "true to report only and write nothing"}
      - {name: seed, type: dir, required: false, from: "evals/demos only: an existing repo layout copied to target first, so the example is never written to (evals/fixtures/repo-existing)"}
    run:
      - {step: seed, kind: script, cmd: "python3 -I scripts/seed_repo.py --from {seed} --target {target}", skip_if_missing: [seed]}
      - {step: install, kind: script, cmd: "python3 -I scripts/install.py --target {target} [--project {project}] {dry_run} --report-json {out}/install-report.json --report-md {out}/install-report.md"}
    outputs:
      - {path: "{out}/install-report.json", checks: [exists, json, contains:"written"]}
      - {path: "{out}/install-report.md", checks: [exists, sections:["Written","Proposed","Env vars","Next steps"]]}
    modes:
      new: {case: agent-happy-path, bring: "an empty or brand-new app folder"}
      existing: {case: agent-mode-existing, bring: "your running app's repo, logger and env file included"}
---

# observability-setup

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/observability-setup --input <name>=<value> … --out <dir>` (see `--explain build/observability-setup`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. Existing files are never overwritten: a differing file gets a `.proposed` twin listed in the report for a manual merge.

## Starting points
- **New** — point `target` at an empty folder: logger, health routes, alert rules, SLO doc and `.env.example` are written.
- **Existing** — point `target` at your repo: files you already have are never overwritten (a different one gets a `.proposed` copy to merge), missing env vars are appended to your `.env.example`, and every `console.*` call in your source is listed for replacement.

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
- `scripts/install.py` — installs the assets into a repo without overwriting (`.proposed` twins), appends env vars to `.env.example`
