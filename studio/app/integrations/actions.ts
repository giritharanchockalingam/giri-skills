"use server";
/* Sync a provider into the catalog now (authors and admins). */
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireWorkspace } from "@/lib/factory/db";
import { syncProvider } from "@/lib/integrations/sync";

export interface SyncState { ok: boolean; message: string; problems: string[] }
const P = z.enum(["vercel", "supabase"]);

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
