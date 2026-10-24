// POST /api/port/sync — drain the Port outbox now (operator token or Vercel cron). Also invoked in the background right
// after every publish / retire, so Port normally reflects a release within seconds; this route is the catch-up path.
import { NextResponse, type NextRequest } from "next/server";
import { operatorAuthorized } from "@/lib/integrations/port/serverAuth";
import { adminConfigured, createAdminSupabase } from "@/lib/supabase/server-admin";
import { drainPortOutbox } from "@/lib/integrations/port/outbox";
import { portalBase, registryRepo } from "@/lib/integrations/port/env";
import { log } from "@/lib/logger";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

async function handle(req: NextRequest) {
  const auth = operatorAuthorized(req.headers.get("authorization"));
  if (!auth.ok) return NextResponse.json({ error: { code: "AUTH_REQUIRED", message: auth.message } }, { status: auth.status });
  if (!adminConfigured()) return NextResponse.json({ error: { code: "NOT_CONFIGURED", message: "SUPABASE_SERVICE_ROLE_KEY is not set on the server" } }, { status: 503 });
  const r = await drainPortOutbox(createAdminSupabase(), { portalBase: portalBase(req), registryRepo: registryRepo() });
  log.info({ action: "port.outbox.drain", ...r, problems: r.problems.length }, "port outbox drained");
  return NextResponse.json(r, { status: r.configured ? 200 : 503 });
}
export const POST = handle;
export const GET = handle; // Vercel cron uses GET
