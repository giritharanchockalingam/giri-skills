/* GitHub webhook receiver: intake in lib/automations/receive.ts (signature, de-duplication); processing runs after
 * the response (next/server after) so GitHub's 10 s window is always met. */
import { NextResponse, after } from "next/server";
import { receiveWebhook } from "@/lib/automations/receive";
import { processEvent, defaultDeps } from "@/lib/automations/process";
import { adminConfigured, createAdminSupabase, ADMIN_MISSING } from "@/lib/supabase/server-admin";
import { log } from "@/lib/logger";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST(req: Request) {
  const origin = new URL(req.url).origin;
  const r = await receiveWebhook(await req.text(), req.headers, {
    secret: process.env.GITHUB_WEBHOOK_SECRET ?? "",
    adminReady: adminConfigured(),
    adminMissing: ADMIN_MISSING,
    sb: createAdminSupabase,
    schedule: (e, delivery, sb) => after(async () => {
      try { log.info({ action: "github.webhook", event: e.kind, delivery, ...(await processEvent(e, delivery, origin, defaultDeps(sb))) }, "webhook processed"); }
      catch (err) { log.error({ action: "github.webhook", event: e.kind, delivery, err }, "webhook processing failed"); }
    }),
  });
  return NextResponse.json(r.body, { status: r.status });
}
