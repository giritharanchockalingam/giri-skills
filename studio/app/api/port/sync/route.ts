// POST /api/port/sync — drain the Port outbox now (operator token or Vercel cron). Also invoked in the background right
// after every publish / retire, so Port normally reflects a release within seconds; this route is the catch-up path.
import { NextResponse, type NextRequest } from "next/server";
import { operatorAuthorized } from "@/lib/integrations/port/serverAuth";
import { adminConfigured, createAdminSupabase } from "@/lib/supabase/server-admin";
import { drainPortOutbox } from "@/lib/integrations/port/outbox";
import { portalBase, registryRepo } from "@/lib/integrations/port/env";
import { log } from "@/lib/logger";
import { PortClient, portConfig } from "@/lib/integrations/port/client";
import { syncMcpServerEntity } from "@/lib/integrations/port/mcpEntity";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

async function handle(req: NextRequest) {
  const auth = operatorAuthorized(req.headers.get("authorization"));
  if (!auth.ok) return NextResponse.json({ error: { code: "AUTH_REQUIRED", message: auth.message } }, { status: auth.status });
  if (!adminConfigured()) return NextResponse.json({ error: { code: "NOT_CONFIGURED", message: "SUPABASE_SERVICE_ROLE_KEY is not set on the server" } }, { status: 503 });
  const admin = createAdminSupabase();
  const r = await drainPortOutbox(admin, { portalBase: portalBase(req), registryRepo: registryRepo() });
  // ?mcp=1 refreshes the MCP server's tool list even when the outbox was empty
  const ws = req.nextUrl.searchParams.get("workspace");
  const cfg = portConfig(process.env);
  if (req.nextUrl.searchParams.get("mcp") === "1" && ws && cfg.ok && !r.mcp) {
    const { data: pub } = await admin.from("sf_skills").select("slug").eq("workspace_id", ws).eq("status", "published");
    try { r.mcp = await syncMcpServerEntity(new PortClient(cfg), portalBase(req), ((pub ?? []) as { slug: string }[]).map((p) => p.slug)); }
    catch (e) { r.problems.push(`MCP server entity: ${(e as Error).message}`); }
  }
  log.info({ action: "port.outbox.drain", ...r, problems: r.problems.length }, "port outbox drained");
  return NextResponse.json(r, { status: r.configured ? 200 : 503 });
}
export const POST = handle;
export const GET = handle; // Vercel cron uses GET
