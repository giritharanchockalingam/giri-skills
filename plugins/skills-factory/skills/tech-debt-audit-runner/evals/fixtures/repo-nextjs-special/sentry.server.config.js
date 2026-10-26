export const dsn = process.env.SENTRY_DSN || "";
export function init() {
  return { dsn, tracesSampleRate: 0.1 };
}
