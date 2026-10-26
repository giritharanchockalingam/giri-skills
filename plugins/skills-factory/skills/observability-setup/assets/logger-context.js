// lib/logger/context.js — request-scoped context via AsyncLocalStorage (node runtime).
import { AsyncLocalStorage } from "node:async_hooks";

/**
 * @typedef {Object} LogContext
 * @property {string} [requestId]
 * @property {string} [vercelId]
 * @property {string} [userId]
 * @property {string} [tenantId]
 * @property {string} [route]
 */

/** @type {AsyncLocalStorage<LogContext>} */
const als = new AsyncLocalStorage();

/** @returns {LogContext} */
export function getLogContext() {
  return als.getStore() ?? {};
}

/**
 * Run fn with a fresh context (call at the top of a route handler / action / job).
 * @template T
 * @param {LogContext} ctx
 * @param {() => T} fn
 * @returns {T}
 */
export function withLogContext(ctx, fn) {
  return als.run({ ...getLogContext(), ...ctx }, fn);
}

/**
 * Enrich the current context (e.g. after requireUser()). No-op outside a context.
 * @param {Partial<LogContext>} patch
 */
export function enrichLogContext(patch) {
  const store = als.getStore();
  if (store) Object.assign(store, patch);
}

/**
 * Derive ids from incoming headers (used by middleware and route handlers).
 * @param {Headers} h
 * @param {string} [route]
 * @returns {LogContext}
 */
export function contextFromHeaders(h, route) {
  return {
    requestId: h.get("x-request-id") ?? crypto.randomUUID(),
    vercelId: h.get("x-vercel-id") ?? undefined,
    route,
  };
}
