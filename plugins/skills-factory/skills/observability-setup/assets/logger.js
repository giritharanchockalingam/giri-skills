// lib/logger.js — structured JSON logger with redaction and request context. No deps.
import { getLogContext } from "./logger/context";

/** @typedef {"debug" | "info" | "warn" | "error"} Level */
/** @type {Record<Level, number>} */
const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };

const REDACT_KEYS = /^(password|passwd|secret|token|authorization|cookie|set-cookie|apikey|api_key|key|email|phone|ssn|card|iban|dsn)$/i;
const MAX_STR = 2048;
const MAX_DEPTH = 5;

const minLevel = LEVELS[process.env.LOG_LEVEL ?? (process.env.NODE_ENV === "production" ? "info" : "debug")] ?? 20;
const pretty = process.env.NODE_ENV === "development" && process.env.LOG_PRETTY === "1";

const base = {
  service: process.env.SERVICE_NAME ?? "web",
  env: process.env.VERCEL_ENV ?? process.env.NODE_ENV ?? "development",
  version: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "local",
};

/**
 * @param {unknown} value
 * @param {number} [depth]
 * @returns {unknown}
 */
export function redact(value, depth = 0) {
  if (depth > MAX_DEPTH) return "[depth]";
  if (typeof value === "string") return value.length > MAX_STR ? `${value.slice(0, MAX_STR)}…[+${value.length - MAX_STR}]` : value;
  if (value instanceof Error) return serializeError(value);
  if (Array.isArray(value)) return value.map((v) => redact(v, depth + 1));
  if (value && typeof value === "object") {
    /** @type {Record<string, unknown>} */
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = REDACT_KEYS.test(k) ? "[redacted]" : redact(v, depth + 1);
    }
    return out;
  }
  return value;
}

/**
 * @param {unknown} e
 * @returns {{ name: string, message: string, code?: string, stack?: string }}
 */
export function serializeError(e) {
  if (e instanceof Error) {
    const code = /** @type {{ code?: string }} */ (e).code;
    // stack is always captured here; emit() drops it below `error` level
    return { name: e.name, message: e.message, ...(code ? { code } : {}), stack: e.stack };
  }
  return { name: "NonError", message: String(e) };
}

/**
 * @param {Level} level
 * @param {Record<string, unknown> | undefined} ctx
 * @param {string} msg
 */
function emit(level, ctx, msg) {
  if (LEVELS[level] < minLevel) return;
  const { err, ...rest } = ctx ?? {};
  const line = {
    ts: new Date().toISOString(),
    level,
    msg,
    ...base,
    ...getLogContext(),
    .../** @type {Record<string, unknown>} */ (redact(rest)),
    ...(err !== undefined ? { err: level === "error" ? serializeError(err) : { ...serializeError(err), stack: undefined } } : {}),
  };
  const out = pretty ? `${line.ts} ${level.toUpperCase().padEnd(5)} ${msg} ${JSON.stringify(rest)}` : JSON.stringify(line);
  // eslint-disable-next-line no-console
  (level === "error" ? console.error : level === "warn" ? console.warn : console.log)(out);
}

/**
 * @typedef {{ (msg: string): void; (ctx: Record<string, unknown>, msg: string): void }} LogFn
 */
/** @param {Level} level @returns {LogFn} */
const make = (level) => (a, b) => (typeof a === "string" ? emit(level, undefined, a) : emit(level, a, b ?? ""));

export const log = {
  debug: make("debug"),
  info: make("info"),
  warn: make("warn"),
  error: make("error"),
  /**
   * Time an operation and log its outcome once.
   * @template T
   * @param {string} action
   * @param {() => Promise<T>} fn
   * @param {Record<string, unknown>} [ctx]
   * @returns {Promise<T>}
   */
  async time(action, fn, ctx = {}) {
    const started = Date.now();
    try {
      const v = await fn();
      emit("info", { ...ctx, action, outcome: "ok", durationMs: Date.now() - started }, "operation completed");
      return v;
    } catch (err) {
      emit("error", { ...ctx, action, outcome: "THREW", durationMs: Date.now() - started, err }, "operation failed");
      throw err;
    }
  },
};
