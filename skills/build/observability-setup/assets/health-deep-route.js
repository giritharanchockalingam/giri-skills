// app/api/health/deep/route.js — readiness. Checks each dependency with a timeout. Bearer-protected.
import "server-only";
import { NextResponse } from "next/server";
import { log } from "@/lib/logger";
import { createAdminClient } from "@/lib/supabase/admin"; // rls-lint: allow — health check only, read-only

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** @typedef {"ok" | "degraded" | "down"} CheckStatus */
/** @typedef {{ status: CheckStatus, latencyMs: number, error?: string, detail?: string }} Check */

const TIMEOUT_MS = 3000;
const SLOW_MS = 1500;
const REQUIRED = new Set(["db", "auth"]);

/**
 * @template T
 * @param {Promise<T>} p
 * @param {number} [ms]
 * @returns {Promise<T>}
 */
async function withTimeout(p, ms = TIMEOUT_MS) {
  let t;
  const timeout = new Promise((_, rej) => { t = setTimeout(() => rej(new Error("timeout")), ms); });
  try { return await Promise.race([p, timeout]); } finally { clearTimeout(t); }
}

/**
 * @param {string} name
 * @param {() => Promise<void>} fn
 * @returns {Promise<[string, Check]>}
 */
async function run(name, fn) {
  const started = Date.now();
  try {
    await withTimeout(fn());
    const latencyMs = Date.now() - started;
    return [name, { status: latencyMs > SLOW_MS ? "degraded" : "ok", latencyMs, ...(latencyMs > SLOW_MS ? { detail: "slow" } : {}) }];
  } catch (e) {
    return [name, { status: "down", latencyMs: Date.now() - started, error: e instanceof Error ? e.message : String(e) }];
  }
}

/** @param {import("next/server").NextRequest} req */
export async function GET(req) {
  const token = process.env.HEALTH_CHECK_TOKEN;
  if (token && req.headers.get("authorization") !== `Bearer ${token}`) {
    return NextResponse.json({ error: { code: "AUTH_REQUIRED", message: "unauthorized" } }, { status: 401 });
  }
  const simulate = process.env.VERCEL_ENV !== "production" ? req.nextUrl.searchParams.get("simulate") : null;

  const admin = createAdminClient(); // rls-lint: allow — health check only, read-only (select 1 / list buckets)
  /** @type {Record<string, Check>} */
  const checks = Object.fromEntries(
    await Promise.all([
      run("db", async () => {
        if (simulate === "error") throw new Error("simulated");
        if (simulate === "slow") await new Promise((r) => setTimeout(r, SLOW_MS + 100));
        const { error } = await admin.rpc("health_ping"); // `create function app.health_ping() returns int language sql as $$ select 1 $$;`
        if (error) throw new Error(error.message);
      }),
      run("auth", async () => {
        const res = await fetch(`${process.env.NEXT_PUBLIC_SUPABASE_URL}/auth/v1/health`, { cache: "no-store" });
        if (!res.ok) throw new Error(`auth ${res.status}`);
      }),
      run("storage", async () => {
        const { error } = await admin.storage.listBuckets();
        if (error) throw new Error(error.message);
      }),
    ]),
  );

  const required = Object.entries(checks).filter(([n]) => REQUIRED.has(n));
  /** @type {CheckStatus} */
  const status = required.some(([, c]) => c.status === "down")
    ? "down"
    : Object.values(checks).some((c) => c.status !== "ok") ? "degraded" : "ok";

  if (status !== "ok") log[status === "down" ? "error" : "warn"]({ action: "health.deep", checks }, "health check not ok");

  return NextResponse.json(
    { status, version: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "local", env: process.env.VERCEL_ENV ?? "development", ts: new Date().toISOString(), checks },
    { status: status === "down" ? 503 : 200, headers: { "Cache-Control": "no-store" } },
  );
}
