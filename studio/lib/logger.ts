// lib/logger.ts — structured JSON logger with redaction and request context. No deps.
import { getLogContext } from "./logger/context";

type Level = "debug" | "info" | "warn" | "error";
const LEVELS: Record<Level, number> = { debug: 10, info: 20, warn: 30, error: 40 };

const REDACT_KEYS = /^(password|passwd|secret|token|authorization|cookie|set-cookie|apikey|api_key|key|email|phone|ssn|card|iban|dsn)$/i;
const MAX_STR = 2048;
const MAX_DEPTH = 5;

const minLevel: number = LEVELS[(process.env.LOG_LEVEL as Level) ?? (process.env.NODE_ENV === "production" ? "info" : "debug")] ?? 20;
const pretty = process.env.NODE_ENV === "development" && process.env.LOG_PRETTY === "1";

const base = {
  service: process.env.SERVICE_NAME ?? "web",
  env: process.env.VERCEL_ENV ?? process.env.NODE_ENV ?? "development",
  version: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "local",
};

export function redact(value: unknown, depth = 0): unknown {
  if (depth > MAX_DEPTH) return "[depth]";
  if (typeof value === "string") return value.length > MAX_STR ? `${value.slice(0, MAX_STR)}…[+${value.length - MAX_STR}]` : value;
  if (value instanceof Error) return serializeError(value);
  if (Array.isArray(value)) return value.map((v) => redact(v, depth + 1));
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = REDACT_KEYS.test(k) ? "[redacted]" : redact(v, depth + 1);
    }
    return out;
  }
  return value;
}

export function serializeError(e: unknown): { name: string; message: string; code?: string; stack?: string } {
  if (e instanceof Error) {
    const code = (e as { code?: string }).code;
    // stack is always captured here; emit() drops it below `error` level
    return { name: e.name, message: e.message, ...(code ? { code } : {}), stack: e.stack };
  }
  return { name: "NonError", message: String(e) };
}

function emit(level: Level, ctx: Record<string, unknown> | undefined, msg: string) {
  if (LEVELS[level] < minLevel) return;
  const { err, ...rest } = ctx ?? {};
  const line = {
    ts: new Date().toISOString(),
    level,
    msg,
    ...base,
    ...getLogContext(),
    ...(redact(rest) as Record<string, unknown>),
    ...(err !== undefined ? { err: level === "error" ? serializeError(err) : { ...serializeError(err), stack: undefined } } : {}),
  };
  const out = pretty ? `${line.ts} ${level.toUpperCase().padEnd(5)} ${msg} ${JSON.stringify(rest)}` : JSON.stringify(line);
  // eslint-disable-next-line no-console
  (level === "error" ? console.error : level === "warn" ? console.warn : console.log)(out);
}

type LogFn = {
  (msg: string): void;
  (ctx: Record<string, unknown>, msg: string): void;
};
const make = (level: Level): LogFn => ((a: unknown, b?: string) => (typeof a === "string" ? emit(level, undefined, a) : emit(level, a as Record<string, unknown>, b ?? ""))) as LogFn;

export const log = {
  debug: make("debug"),
  info: make("info"),
  warn: make("warn"),
  error: make("error"),
  /** Time an operation and log its outcome once. */
  async time<T>(action: string, fn: () => Promise<T>, ctx: Record<string, unknown> = {}): Promise<T> {
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
