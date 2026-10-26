// Health endpoint for uptime monitors and the ops runbook.
// GET /api/health -> { ok, checks, version, ts }; 503 when a dependency is unreachable.
import { SUPABASE_URL, SUPABASE_ANON_KEY } from "../../../lib/config";

export const runtime = "edge";
export const dynamic = "force-dynamic";

async function probe(url, headers) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 3000);
  try {
    const r = await fetch(url, { headers, signal: ctrl.signal, cache: "no-store" });
    return r.status > 0 && r.status < 500;
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}

export async function GET() {
  const [db, auth] = await Promise.all([
    probe(`${SUPABASE_URL}/rest/v1/`, { apikey: SUPABASE_ANON_KEY }),
    probe(`${SUPABASE_URL}/auth/v1/health`, { apikey: SUPABASE_ANON_KEY }),
  ]);
  const ok = db && auth;
  return Response.json(
    { ok, checks: { db, auth }, version: process.env.GIT_SHA || "dev", ts: new Date().toISOString() },
    { status: ok ? 200 : 503, headers: { "cache-control": "no-store, max-age=0" } }
  );
}
