"use server";
/* Sync a provider into the catalog now (authors and admins). */
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireWorkspace } from "@/lib/factory/db";
import { syncProvider } from "@/lib/integrations/sync";
import { NoFields } from "@/lib/validation";

export interface SyncState { ok: boolean; message: string; problems: string[] }
const P = z.enum(["vercel", "supabase", "port"]);

export async function syncIntegration(_: SyncState | null, fd: FormData): Promise<SyncState> {
  const p = P.safeParse(fd.get("provider"));
  if (!p.success) return { ok: false, message: "Unknown provider.", problems: [] };
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin" && ctx.role !== "author") return { ok: false, message: "Authors and administrators sync integrations.", problems: [] };
  const r = await syncProvider(ctx.supabase, ctx.workspace.id, ctx.user.id, p.data);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: `integration.sync.${p.data}`, p_entity_type: "integration", p_entity_id: p.data, p_details: { ok: r.ok, entities: r.entities, relations: r.relations } });
  // a repository's delivery metrics use its Vercel production deployments once the service is linked
  if (r.ok && p.data === "vercel") { const { refreshDelivery } = await import("@/lib/insights/deliveryRefresh"); await refreshDelivery(ctx.supabase, ctx.workspace.id, ctx.user.id); }
  revalidatePath("/integrations"); revalidatePath("/catalog"); revalidatePath("/insights");
  return { ok: r.ok, message: r.message, problems: r.problems.slice(0, 20) };
}

/** Push every published / retired skill to Port (admins): enqueue one outbox event per skill, then drain. The outbox is
 *  the record; what did not reach Port stays there with its error and is listed on this page. */
export async function syncToPort(_: SyncState | null, fd?: FormData): Promise<SyncState> {
  NoFields.parse(fd);
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") return { ok: false, message: "Administrators push skills to Port.", problems: [] };
  const { data: enq, error } = await ctx.supabase.rpc("sf_port_enqueue_all", { p_workspace: ctx.workspace.id });
  if (error) return { ok: false, message: error.message, problems: [] };
  const { kickPortSync } = await import("@/lib/integrations/port/kick");
  await kickPortSync();
  const { reconcilePort } = await import("@/lib/integrations/port/reconcile");
  const r = await reconcilePort(ctx.supabase, ctx.workspace.id);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "integration.sync.port", p_entity_type: "integration", p_entity_id: "port", p_details: { ok: r.mismatches.length === 0 && !r.error, enqueued: (enq as { events?: number })?.events ?? null, matched: r.matched, mismatches: r.mismatches.length } });
  revalidatePath("/integrations");
  if (r.error) return { ok: false, message: r.error, problems: [] };
  const total = r.factory.published + r.factory.retired;
  return { ok: r.mismatches.length === 0, message: `${r.matched} of ${total} skills match in Port (hash and release state); Port holds ${r.port.published} published, factory ${r.factory.published}.`, problems: r.mismatches.slice(0, 20).map((m) => `${m.slug}: ${m.reason} — ${m.detail}`) };
}
