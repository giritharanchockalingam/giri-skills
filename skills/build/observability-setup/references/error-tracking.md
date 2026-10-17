# Error Tracking (Sentry default; adapt names for another vendor)

## Install
```bash
npm i @sentry/nextjs
npx @sentry/wizard@latest -i nextjs   # or hand-write the three config files below
```
Env: `SENTRY_DSN` (server/edge), `NEXT_PUBLIC_SENTRY_DSN` (client), `SENTRY_AUTH_TOKEN` (CI only, source maps).

## Config files
| File | Runtime | Notes |
|---|---|---|
| `sentry.server.config.ts` | node | `tracesSampleRate` 0.1 prod / 1.0 preview; `beforeSend` scrubs PII |
| `sentry.client.config.ts` | browser | `replaysOnErrorSampleRate` 0.1 if Replay used; mask all text |
| `sentry.edge.config.ts` | edge | minimal |
| `instrumentation.ts` | — | `register()` loads the right config per `process.env.NEXT_RUNTIME` |
| `app/global-error.tsx` | client | `Sentry.captureException(error)` + show `requestId` |
| `next.config.ts` | — | `withSentryConfig(config, { silent: true, widenClientFileUpload: true, hideSourceMaps: true })` |

## Tagging and context
```ts
Sentry.setTag("requestId", ctx.requestId);
Sentry.setTag("tenantId", ctx.tenantId);
Sentry.setUser({ id: ctx.userId });          // id only — never email
Sentry.setTag("release", process.env.VERCEL_GIT_COMMIT_SHA);
```
Do this in `requireUser()` (server) and after sign-in (client).

## Scrubbing (`beforeSend`)
- Drop `request.cookies`, `request.headers.authorization`, `request.data` (bodies).
- Walk `extra`/`contexts` with the same redaction list as the logger.
- `sendDefaultPii: false`.

## What to capture
| Capture | Don't capture |
|---|---|
| Unhandled exceptions (automatic) | expected `Result` failures (4xx) — those are logs at `warn` |
| `INTERNAL` results in services (`Sentry.captureException(error.cause)`) | validation errors |
| Failed jobs after final retry | each retry |
| Client render errors (`global-error.tsx`) | network errors from ad blockers (`ignoreErrors`) |

## Source maps
CI step in `prod.yml` after build: Sentry plugin uploads with `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT`; release = commit sha. Verify one prod event shows de-minified frames.

## Alert integration
Sentry issue alerts: new issue in prod → channel; regression → channel; spike (>10 events/5 min same issue) → page. See `alerts-and-slos.md`.

## Verify
1. Deploy preview; hit `/api/health/deep?simulate=error` (preview only) → event appears with `requestId` tag.
2. Open the event: no email, cookies, or body present.
3. Client: throw in a test button behind `feature.debug` → event with session replay masked.
