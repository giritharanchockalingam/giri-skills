---
name: observability-setup
description: Use when an app is going to production or lacks visibility — "add logging", "set up Sentry", "health checks", "alerts", "we can't see what's failing". Produces structured JSON logging (lib/logger.ts), error tracking wiring, /api/health and /api/health/deep endpoints, alert rules, an SLO starter and a minimal dashboard spec for the Next.js + Supabase + Vercel stack. Not for debugging a specific failure (use safe-fix) or CI (use ci-cd-vercel-github).
license: MIT
metadata:
  domain: build
  adlc_stage: operate
  version: 0.3.0
  author: giri-skills
  fits:
    stacks: [nextjs]
    request_kinds: [hardening, greenfield]
  agent:
    inputs:
      - {name: target, type: path, required: true, from: "Next.js repo root (created if absent)"}
      - {name: project, type: string, required: false, from: "project name for docs/observability.md (default: target dir name)"}
      - {name: dry_run, type: flag, required: false, flag: "--dry-run", from: "true to report only and write nothing"}
      - {name: flavour, type: string, required: false, from: "ts or js to override the detected language flavour (default: tsconfig.json or .ts/.tsx source → ts, else js)"}
      - {name: seed, type: dir, required: false, from: "evals/demos only: an existing repo layout copied to target first, so the example is never written to (evals/fixtures/repo-existing)"}
    run:
      - {step: seed, kind: script, cmd: "python3 -I scripts/seed_repo.py --from {seed} --target {target}", skip_if_missing: [seed]}
      - {step: install, kind: script, cmd: "python3 -I scripts/install.py --target {target} [--project {project}] [--flavour {flavour}] {dry_run} --report-json {out}/install-report.json --report-md {out}/install-report.md"}
    outputs:
      - {path: "{out}/install-report.json", checks: [exists, json, contains:"written"]}
      - {path: "{out}/install-report.md", checks: [exists, sections:["Written","Kept","Proposed","Env vars","Next steps"]]}
    modes:
      new: {case: agent-happy-path, bring: "an empty or brand-new app folder"}
      existing: {case: agent-mode-existing, bring: "your running app's repo, logger and env file included"}
---

# observability-setup

## In a conversation: plan the setup now
- **The request asks for observability on this stack**: answer **in this reply**, in order: (1) one list of questions, asked once — critical user journeys (≤5), error-tracking vendor (Sentry default) and DSN availability, notification channel — each with your default, then carry on with the defaults; (2) the plan table — component → file → add/change → why — covering logger, request context, error tracking, health endpoints, alert rules, SLOs, dashboard, with a line that nothing changes until "go"; (3) logging: `lib/logger.ts` + `lib/logger/context.ts` (JSON fields `ts, level, msg, service, env, requestId`; redaction of email, token, password, authorization, cookie, key; `requestId` set in `middleware.ts`), `console.*` replaced in minimal diffs, ESLint `no-console: error`; (4) health: `app/api/health/route.ts` (liveness, no dependencies) and `app/api/health/deep/route.ts` (bearer-protected, ≤ 3 s timeout per dependency, 503 when one is down), with tests for both; (5) an alert table — alert → threshold → window → severity tier → runbook → owner → channel — and an SLO table per journey with an error-budget policy; (6) verification on preview: force a synthetic failure (deep health 503) and confirm the alert fires end to end, and confirm a test error reaches the tracker tagged with `requestId`. Thresholds and SLO targets the user has not given are `[TO BE BASELINED — owner: ___]`. Never reply with only a request for the repo.
- **Part of it already exists** (e.g. "we already have Sentry"): open with an inventory of what is there (Sentry server/client/edge configs, `global-error.tsx`, tags, source maps) and state that it is kept as is; add only what was asked (e.g. health routes and alert rules); add `requestId` as a Sentry tag only if it is missing, as a minimal diff; touch the logger only if `console.*` calls are found.
- **Bare "add observability"**: ask once, in one list, for the critical journeys and the alert channel; meanwhile show the plan skeleton with every SLO target and alert threshold as `[TO BE BASELINED — owner: ___]`. Never invent SLO numbers.
- **Asked to replace an existing logger or config outright**: decline the overwrite in one line (it loses the team's wiring) and propose the standard file beside it as a `.proposed` twin for a manual merge.

## Starting points
- **New** — point `target` at an empty folder: logger, health routes, alert rules, SLO doc and `.env.example` are written (TypeScript by default).
- **Existing** — point `target` at your repo. **Read before write:** the language flavour is detected first (`tsconfig.json` or any `.ts/.tsx` under `app|lib|components` → TypeScript, otherwise JavaScript) and every file is emitted as `.ts` or `.js` to match — a JavaScript Next.js app gets `lib/logger.js` and `route.js`, never a `.ts` file. A file you already have, **in either extension**, is never overwritten and never gets a conflicting sibling (`route.ts` beside `route.js` is a Next.js routing conflict): an existing health route is reported `exists, kept` with a static gap table (exports `GET`? `force-dynamic`? `no-store`? liveness free of dependency calls?), another existing file in the same flavour gets a `.proposed` twin to merge, one in the other flavour is kept and pointed at the asset. Env vars are appended to `.env.example` only for files written in this run; every `console.*` call in your source is listed. A repo that already has every piece exits 0 with just the gap table; a repo that already holds a conflicting pair (`route.js` **and** `route.ts`) writes nothing, says why in the report, and exits 1.

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

Missing facts do not stop the plan: use the stated defaults, mark thresholds and SLO targets `[TO BE BASELINED — owner: ___]` and ask once at the start. Never invent SLO numbers.

## Procedure
1. Read `../../../shared/stack-conventions.md` (Logging, Errors rows) and `../../../shared/token-efficiency.md`. Inventory what exists: language flavour (`tsconfig.json` / `.ts` source vs `jsconfig.json` / `.js` only), logger, Sentry, health routes in either extension, deploy platform (Vercel or AWS workflows), Next special files. Every file you add takes the repo's extension; never place a `.ts` route or module beside an existing `.js` one.
2. **Plan.** Table of components to add/change: logger, request context, error tracking (server + client + edge), health endpoints, alert rules, SLOs, dashboard, runbook links. Post; wait for "go". *(gate: plan→approve)*
3. **Logging.** Install `assets/logger.ts` (or `assets/logger.js` in a JavaScript repo) as `lib/logger.{ts,js}` (+ `lib/logger/context.{ts,js}` AsyncLocalStorage) per `references/log-schema.md`; wire `requestId` in `middleware.ts`; ESLint `no-console: error`. Replace existing `console.*` in minimal diffs.
4. **Error tracking.** Follow `references/error-tracking.md`: server, client, edge configs; `requestId`/`tenantId` tags; PII scrubbing; source maps in CI; `error.tsx` reporting.
5. **Health.** Add `assets/health-route.ts` (or `.js`) as `app/api/health/route.{ts,js}` (liveness, no deps) and `app/api/health/deep/route.{ts,js}` (DB, auth, storage, queue; bearer-protected) per `references/health-endpoints.md`. If a health route already exists in either extension, keep it, verify it exports `GET`, and list what it is missing versus the standard (see the reference's brownfield table) instead of adding a sibling.
6. **Alerts + SLOs.** From `references/alerts-and-slos.md`, fill `assets/alert-rules.yaml` for the chosen vendor and the SLO table for the critical journeys. Every alert has a runbook link and an owner.
7. **Test.** Unit test logger redaction; integration test both health routes (200 / 503 on simulated DB failure); trigger a test error and confirm it appears in the tracker with `requestId`. Full unit suite green. *(gate: build→test)*
8. **Verify.** Deploy to preview; curl both health routes; confirm Log Drain delivers JSON; confirm an alert fires on a synthetic failure (health 503). *(gate: test→verify)*
9. Write `docs/observability.md` (schema, endpoints, alerts, dashboards, how to find a request by id). Update `docs/HANDOFF.md`.

## Output
| Artifact | Path |
|---|---|
| Logger | `lib/logger.{ts,js}`, `lib/logger/context.{ts,js}` (extension follows the repo) |
| Error tracking | `sentry.{server,client,edge}.config.ts` (or vendor equivalent), `app/global-error.tsx` |
| Health | `app/api/health/route.{ts,js}`, `app/api/health/deep/route.{ts,js}` |
| Alerts / SLOs | `ops/alerts.yaml`, `docs/observability.md` |
| Dashboard spec | `docs/observability.md` §Dashboards |

## Self-check
- [ ] Every log line has `ts, level, msg, service, env`; request-scoped lines have `requestId`
- [ ] Redaction list covers email, token, password, authorization, cookie, key
- [ ] Health liveness has zero dependencies; deep check is auth-protected and times out ≤ 3 s per dependency
- [ ] Every added file matches the repo's flavour (`.js` in a JavaScript repo); no route or module exists in two extensions
- [ ] Every alert: threshold, window, severity, runbook, owner, notification channel
- [ ] SLOs defined for each critical journey with an error-budget policy
- [ ] Synthetic failure produced an alert end-to-end
- [ ] No PII reached the error tracker (checked a real event)

## References
- `references/log-schema.md` — fields, levels, redaction, request context
- `references/error-tracking.md` — Sentry (default) wiring for server/client/edge, scrubbing, source maps
- `references/health-endpoints.md` — liveness vs readiness vs deep; response contract
- `references/alerts-and-slos.md` — alert catalogue, SLO starter, error-budget policy, dashboard panels
- `assets/logger.ts`, `assets/logger-context.ts`, `assets/health-route.ts`, `assets/health-deep-route.ts` (+ the `.js` twins `assets/logger.js`, `assets/logger-context.js`, `assets/health-route.js`, `assets/health-deep-route.js`, functionally identical), `assets/alert-rules.yaml`
- `scripts/install.py` — detects the flavour, installs the matching assets without overwriting or creating `.ts`/`.js` siblings (`exists, kept` + gap table for health routes, `.proposed` twins otherwise), appends env vars for written files to `.env.example`
- `scripts/check_siblings.py` — fails when any route or module exists in two source extensions (used by the eval checks)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs above, then run `python3 scripts/run_skill.py build/observability-setup --input <name>=<value> … --out <dir>` (see `--explain build/observability-setup`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. Existing files are never overwritten and never get a `.ts`/`.js` sibling: a health route that exists is kept and gap-checked, a differing file in the same flavour gets a `.proposed` twin listed in the report for a manual merge, and an existing conflicting pair aborts the run (exit 1, nothing written).
