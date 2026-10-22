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

/** Push published skills to Port as "AI Skill" entities (admins). */
export async function syncToPort(_: SyncState | null, fd?: FormData): Promise<SyncState> {
  NoFields.parse(fd);
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") return { ok: false, message: "Administrators push skills to Port.", problems: [] };
  const { headers } = await import("next/headers");
  const h = await headers();
  const base = `${h.get("x-forwarded-proto") ?? "https"}://${h.get("x-forwarded-host") ?? h.get("host")}`;
  const { syncSkillsToPort } = await import("@/lib/integrations/port/sync");
  const r = await syncSkillsToPort(ctx.supabase, ctx.workspace.id, base);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "integration.sync.port", p_entity_type: "integration", p_entity_id: "port", p_details: { ok: r.ok, pushed: r.pushed, blueprint: r.blueprint ?? null, problems: r.problems.length } });
  revalidatePath("/integrations");
  return { ok: r.ok, message: r.message, problems: r.problems.slice(0, 20) };
}
