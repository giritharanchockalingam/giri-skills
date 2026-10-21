/* POST /api/admin/freeze — admins only. Freezes the reviewed files of every library version past draft in this
 * workspace that has no frozen copy yet, while this deployment still holds those exact files (lib/factory/snapshot.ts).
 * Run before deploying library changes to skills that are in review, approved or published. Idempotent. */
import { apiContext, apiError, json } from "@/lib/factory/http";
import { ensureSnapshot } from "@/lib/factory/snapshot";
import { adminConfigured } from "@/lib/supabase/server-admin";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

export async function POST() {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  if (ctx.role !== "admin") return apiError(403, "forbidden", "Only admins can freeze versions.");
  if (!adminConfigured()) return apiError(503, "not_configured", "The server's service key is not set, so versions cannot be frozen.");
  const { data: rows, error } = await ctx.supabase.from("sf_skill_versions")
    .select("id, status, source, sf_skills!sf_skill_versions_skill_id_fkey!inner(slug, workspace_id)")
    .eq("sf_skills.workspace_id", ctx.workspace.id).neq("status", "draft").eq("source->>kind", "repo");
  if (error) return apiError(500, "query_failed", error.message);
  const { data: have } = await ctx.supabase.from("sf_version_snapshots").select("version_id").eq("workspace_id", ctx.workspace.id);
  const frozen = new Set((have ?? []).map((h: { version_id: string }) => h.version_id));
  const result = { already: 0, frozen: [] as string[], not_frozen: [] as { slug: string; status: string; reason: string }[] };
  for (const v of (rows ?? []) as unknown as { id: string; status: string; sf_skills: { slug: string } }[]) {
    if (frozen.has(v.id)) { result.already++; continue; }
    try {
      const snap = await ensureSnapshot(v.id);
      if (snap) result.frozen.push(v.sf_skills.slug);
      else result.not_frozen.push({ slug: v.sf_skills.slug, status: v.status, reason: "this deployment no longer holds the files the version was reviewed with" });
    } catch (e) {
      result.not_frozen.push({ slug: v.sf_skills.slug, status: v.status, reason: (e as Error).message });
    }
  }
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "version.freeze", p_entity_type: "workspace", p_entity_id: ctx.workspace.id, p_details: { frozen: result.frozen.length, already: result.already, not_frozen: result.not_frozen.length } });
  return json(result);
}
