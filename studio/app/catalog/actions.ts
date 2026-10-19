"use server";
/* Catalog actions: start the GitHub install (signed state), sync now, disconnect. RLS enforces roles; checked here too. */
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { githubConfig, signState, GITHUB_WEB } from "@/lib/github/app";
import { syncWorkspace } from "@/lib/github/sync";
import { fromForm, NoFields, NoArgs, DisconnectGithubForm, EntityIdArg } from "@/lib/validation";

export interface SyncResult { ok: boolean; message: string; errors?: string[] }

export async function connectGithub(form?: FormData) {
  NoFields.parse(form);
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") redirect("/catalog?error=admin-only");
  const c = githubConfig();
  if (!c.ok) redirect("/catalog?error=not-configured");
  redirect(`${GITHUB_WEB}/apps/${encodeURIComponent(c.cfg.slug)}/installations/new?state=${encodeURIComponent(signState({ w: ctx.workspace.id, u: ctx.user.id }, c.cfg.clientSecret))}`);
}

export async function syncNow(args?: undefined): Promise<SyncResult> {
  NoArgs.parse(args);
  const ctx = await requireWorkspace();
  if (!["admin", "author"].includes(ctx.role)) return { ok: false, message: "Authors and administrators can sync." };
  const r = await syncWorkspace(ctx.supabase, ctx.workspace.id, ctx.user.id);
  revalidatePath("/catalog");
  return { ok: r.ok, message: r.message, errors: r.errors.slice(0, 10) };
}

export async function disconnectGithub(formData: FormData) {
  const { installation_id: id } = DisconnectGithubForm.parse(fromForm(DisconnectGithubForm, formData));
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") redirect("/catalog?error=admin-only");
  if (!Number.isSafeInteger(id)) redirect("/catalog?error=bad-request");
  await ctx.supabase.from("sf_catalog_entities").delete().eq("workspace_id", ctx.workspace.id).eq("installation_id", id);
  await ctx.supabase.from("sf_github_installations").delete().eq("workspace_id", ctx.workspace.id).eq("installation_id", id);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "github.disconnect", p_entity_type: "github_installation", p_entity_id: String(id), p_details: {} });
  revalidatePath("/catalog");
  redirect("/catalog?disconnected=1");
}

/** Score one repository (the UI calls this per repository so each request stays within the time limit). */
export async function scoreRepository(entityId: string) {
  const parsed = EntityIdArg.safeParse(entityId);
  const ctx = await requireWorkspace();
  if (!["admin", "author"].includes(ctx.role)) return { ok: false, entity: entityId, message: "Authors and administrators can run scorecards.", results: [] };
  if (!parsed.success) return { ok: false, entity: entityId, message: "bad id", results: [] };
  const { scoreEntity } = await import("@/lib/scorecards/run");
  try {
    const r = await scoreEntity(ctx.supabase, ctx.workspace.id, ctx.user.id, entityId);
    if (r.results.length) await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "scorecard.run", p_entity_type: "catalog_entity", p_entity_id: entityId,
      p_details: { repo: r.entity, verdicts: Object.fromEntries(r.results.map((x) => [x.check, x.verdict])) } });
    return r;
  } catch (e) {
    return { ok: false, entity: entityId, message: (e as Error).message.slice(0, 300), results: [] };
  } finally {
    revalidatePath("/catalog");
  }
}
