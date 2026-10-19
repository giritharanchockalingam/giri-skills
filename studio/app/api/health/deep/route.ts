// app/api/health/deep/route.ts — readiness. Checks each dependency with a timeout. Bearer-protected.
// Installed by the observability-setup skill; checks adapted to this portal, which has NO service-role client:
// db = sf_health_ping() over the anon role (migration 0010), auth = Supabase auth health, runtime = the Python
// function, github = App configuration present (no call: it would need an installation token).
import { NextResponse, type NextRequest } from "next/server";
import { log } from "@/lib/logger";
import { createAnonSupabase } from "@/lib/supabase/server";
import { SUPABASE_URL, SUPABASE_ANON_KEY } from "@/lib/supabase/env";
import { runtimeHealth } from "@/lib/factory/runtime";
import { githubConfig } from "@/lib/github/app";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type CheckStatus = "ok" | "degraded" | "down";
type Check = { status: CheckStatus; latencyMs: number; error?: string; detail?: string };

const TIMEOUT_MS = 3000;
const SLOW_MS = 1500;
const REQUIRED = new Set(["db", "auth", "runtime"]);

async function withTimeout<T>(p: Promise<T>, ms = TIMEOUT_MS): Promise<T> {
  let t: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, rej) => { t = setTimeout(() => rej(new Error("timeout")), ms); });
  try { return await Promise.race([p, timeout]); } finally { clearTimeout(t); }
}

async function run(name: string, fn: () => Promise<void>): Promise<[string, Check]> {
  const started = Date.now();
  try {
    await withTimeout(fn());
    const latencyMs = Date.now() - started;
    return [name, { status: latencyMs > SLOW_MS ? "degraded" : "ok", latencyMs, ...(latencyMs > SLOW_MS ? { detail: "slow" } : {}) }];
  } catch (e) {
    return [name, { status: "down", latencyMs: Date.now() - started, error: e instanceof Error ? e.message : String(e) }];
  }
}

export async function GET(req: NextRequest) {
  const token = process.env.HEALTH_CHECK_TOKEN;
  // production never answers without the token: dependency status is reconnaissance for an attacker
  if (!token && process.env.VERCEL_ENV === "production") {
    return NextResponse.json({ error: { code: "NOT_CONFIGURED", message: "set HEALTH_CHECK_TOKEN to enable the deep health check" } }, { status: 401 });
  }
  if (token && req.headers.get("authorization") !== `Bearer ${token}`) {
    return NextResponse.json({ error: { code: "AUTH_REQUIRED", message: "unauthorized" } }, { status: 401 });
  }
  const simulate = process.env.VERCEL_ENV !== "production" ? req.nextUrl.searchParams.get("simulate") : null;

  const checks = Object.fromEntries(
    await Promise.all([
      run("db", async () => {
        if (simulate === "error") throw new Error("simulated");
        if (simulate === "slow") await new Promise((r) => setTimeout(r, SLOW_MS + 100));
        const { data, error } = await createAnonSupabase().rpc("sf_health_ping");
        if (error) throw new Error(error.message);
        if (data !== 1) throw new Error("unexpected ping result");
      }),
      run("auth", async () => {
        const res = await fetch(`${SUPABASE_URL}/auth/v1/health`, { cache: "no-store", headers: { apikey: SUPABASE_ANON_KEY } });
        if (!res.ok) throw new Error(`auth ${res.status}`);
      }),
      run("runtime", async () => {
        const h = await runtimeHealth();
        if (!h.ok) throw new Error(h.error ?? "runtime not healthy");
      }),
      run("github", async () => {
        const c = githubConfig();
        if (!c.ok) throw new Error(`not configured: ${c.missing.join(", ")}`);
      }),
    ]),
  ) as Record<string, Check>;

  const required = Object.entries(checks).filter(([n]) => REQUIRED.has(n));
  const status: CheckStatus = required.some(([, c]) => c.status === "down")
    ? "down"
    : Object.values(checks).some((c) => c.status !== "ok") ? "degraded" : "ok";

  if (status !== "ok") log[status === "down" ? "error" : "warn"]({ action: "health.deep", checks }, "health check not ok");

  return NextResponse.json(
    { status, version: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "local", env: process.env.VERCEL_ENV ?? "development", ts: new Date().toISOString(), checks },
    { status: status === "down" ? 503 : 200, headers: { "Cache-Control": "no-store" } },
  );
}
