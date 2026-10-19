"use server";
/* Catalog actions: start the GitHub install (signed state), sync now, disconnect. RLS enforces roles; checked here too. */
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { githubConfig, signState, GITHUB_WEB } from "@/lib/github/app";
import { syncWorkspace } from "@/lib/github/sync";

export async function connectGithub() {
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") redirect("/catalog?error=admin-only");
  const c = githubConfig();
  if (!c.ok) redirect("/catalog?error=not-configured");
  redirect(`${GITHUB_WEB}/apps/${encodeURIComponent(c.cfg.slug)}/installations/new?state=${encodeURIComponent(signState({ w: ctx.workspace.id, u: ctx.user.id }, c.cfg.clientSecret))}`);
}

export async function syncNow(): Promise<{ ok: boolean; message: string; errors?: string[] }> {
  const ctx = await requireWorkspace();
  if (!["admin", "author"].includes(ctx.role)) return { ok: false, message: "Authors and administrators can sync." };
  const r = await syncWorkspace(ctx.supabase, ctx.workspace.id, ctx.user.id);
  revalidatePath("/catalog");
  return { ok: r.ok, message: r.message, errors: r.errors.slice(0, 10) };
}

export async function disconnectGithub(formData: FormData) {
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") redirect("/catalog?error=admin-only");
  const id = Number(formData.get("installation_id"));
  if (!Number.isSafeInteger(id)) redirect("/catalog?error=bad-request");
  await ctx.supabase.from("sf_catalog_entities").delete().eq("workspace_id", ctx.workspace.id).eq("installation_id", id);
  await ctx.supabase.from("sf_github_installations").delete().eq("workspace_id", ctx.workspace.id).eq("installation_id", id);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "github.disconnect", p_entity_type: "github_installation", p_entity_id: String(id), p_details: {} });
  revalidatePath("/catalog");
  redirect("/catalog?disconnected=1");
}
