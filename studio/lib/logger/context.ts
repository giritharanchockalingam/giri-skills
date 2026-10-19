// lib/logger/context.ts — request-scoped context via AsyncLocalStorage (node runtime).
import { AsyncLocalStorage } from "node:async_hooks";

export type LogContext = {
  requestId?: string;
  vercelId?: string;
  userId?: string;
  tenantId?: string;
  route?: string;
};

const als = new AsyncLocalStorage<LogContext>();

export function getLogContext(): LogContext {
  return als.getStore() ?? {};
}

/** Run fn with a fresh context (call at the top of a route handler / action / job). */
export function withLogContext<T>(ctx: LogContext, fn: () => T): T {
  return als.run({ ...getLogContext(), ...ctx }, fn);
}

/** Enrich the current context (e.g. after requireUser()). No-op outside a context. */
export function enrichLogContext(patch: Partial<LogContext>): void {
  const store = als.getStore();
  if (store) Object.assign(store, patch);
}

/** Derive ids from incoming headers (used by middleware and route handlers). */
export function contextFromHeaders(h: Headers, route?: string): LogContext {
  return {
    requestId: h.get("x-request-id") ?? crypto.randomUUID(),
    vercelId: h.get("x-vercel-id") ?? undefined,
    route,
  };
}
