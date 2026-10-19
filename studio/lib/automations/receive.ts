/* GitHub webhook intake, independent of Next: verify the signature, ignore what we don't act on, record the
 * delivery id once (GitHub retries and redeliveries become no-ops), then hand the event to `schedule` so the
 * caller can answer inside GitHub's 10 s window and process afterwards. Returns status + JSON body. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { verifySignature, normalize, type NormEvent } from "./webhook";

export interface ReceiveDeps {
  secret: string;
  adminReady: boolean;
  adminMissing: string;
  sb: () => SupabaseClient;
  schedule: (e: NormEvent, delivery: string, sb: SupabaseClient) => void;
  newId?: () => string;
}
export interface Reply { status: number; body: Record<string, unknown> }
const err = (status: number, code: string, message: string): Reply => ({ status, body: { error: { code, message } } });

export async function receiveWebhook(raw: string, headers: Headers, d: ReceiveDeps): Promise<Reply> {
  if (!d.secret) return err(401, "bad_signature", "GITHUB_WEBHOOK_SECRET is not set");
  if (!verifySignature(raw, headers.get("x-hub-signature-256"), d.secret)) return err(401, "bad_signature", "signature mismatch");
  const event = headers.get("x-github-event") ?? "";
  const delivery = (headers.get("x-github-delivery") ?? "").slice(0, 100) || (d.newId ?? (() => crypto.randomUUID()))();
  if (event === "ping") return { status: 200, body: { ok: true, pong: true } };
  if (!d.adminReady) return err(503, "not_configured", d.adminMissing);
  let payload: Record<string, unknown>;
  try { payload = JSON.parse(raw); } catch { return err(400, "bad_request", "body is not JSON"); }
  const e = normalize(event, payload);
  if (!e) return { status: 200, body: { ok: true, ignored: event } };

  const sb = d.sb();
  const { data: inst, error: instErr } = await sb.from("sf_github_installations").select("workspace_id").eq("installation_id", e.installationId).maybeSingle();
  if (instErr) return err(500, "store_failed", instErr.message);
  if (!inst) return { status: 200, body: { ok: true, ignored: "installation not linked to a workspace" } };
  const { data: fresh, error } = await sb.from("sf_github_deliveries")
    .upsert({ delivery_id: delivery, workspace_id: inst.workspace_id, event, installation_id: e.installationId }, { onConflict: "delivery_id", ignoreDuplicates: true })
    .select("delivery_id");
  if (error) return err(500, "store_failed", error.message);
  if (!fresh?.length) return { status: 200, body: { ok: true, duplicate: delivery } };
  d.schedule(e, delivery, sb);
  return { status: 202, body: { ok: true, accepted: e.kind } };
}
