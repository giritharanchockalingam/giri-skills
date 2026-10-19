/* GitHub webhook receiver. Verifies the signature (GITHUB_WEBHOOK_SECRET), records the delivery id once (GitHub
 * retries are no-ops), answers within GitHub's 10 s window, and processes the event after responding. */
import { NextResponse, after } from "next/server";
import { verifySignature, normalize } from "@/lib/automations/webhook";
import { processEvent } from "@/lib/automations/process";
import { adminConfigured, createAdminSupabase, ADMIN_MISSING } from "@/lib/supabase/server-admin";
import { log } from "@/lib/logger";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST(req: Request) {
  const secret = process.env.GITHUB_WEBHOOK_SECRET ?? "";
  const raw = await req.text();
  if (!secret || !verifySignature(raw, req.headers.get("x-hub-signature-256"), secret)) {
    return NextResponse.json({ error: { code: "bad_signature", message: secret ? "signature mismatch" : "GITHUB_WEBHOOK_SECRET is not set" } }, { status: 401 });
  }
  const event = req.headers.get("x-github-event") ?? "";
  const delivery = (req.headers.get("x-github-delivery") ?? "").slice(0, 100);
  if (event === "ping") return NextResponse.json({ ok: true, pong: true });
  if (!adminConfigured()) return NextResponse.json({ error: { code: "not_configured", message: ADMIN_MISSING } }, { status: 503 });
  let payload: Record<string, unknown>;
  try { payload = JSON.parse(raw); } catch { return NextResponse.json({ error: { code: "bad_request", message: "body is not JSON" } }, { status: 400 }); }
  const e = normalize(event, payload);
  if (!e) return NextResponse.json({ ok: true, ignored: event });

  const sb = createAdminSupabase();
  const { data: inst } = await sb.from("sf_github_installations").select("workspace_id").eq("installation_id", e.installationId).maybeSingle();
  if (!inst) return NextResponse.json({ ok: true, ignored: "installation not linked to a workspace" });
  const { data: fresh, error } = await sb.from("sf_github_deliveries")
    .upsert({ delivery_id: delivery || crypto.randomUUID(), workspace_id: inst.workspace_id, event, installation_id: e.installationId }, { onConflict: "delivery_id", ignoreDuplicates: true }).select("delivery_id");
  if (error) return NextResponse.json({ error: { code: "store_failed", message: error.message } }, { status: 500 });
  if (!fresh?.length) return NextResponse.json({ ok: true, duplicate: delivery });

  const origin = new URL(req.url).origin;
  after(async () => {
    try { log.info({ action: "github.webhook", event, delivery, ...(await processEvent(e, delivery, origin, sb)) }, "webhook processed"); }
    catch (err) { log.error({ action: "github.webhook", event, delivery, err }, "webhook processing failed"); }
  });
  return NextResponse.json({ ok: true, accepted: e.kind }, { status: 202 });
}
