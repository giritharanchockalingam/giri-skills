/* Compute and store delivery snapshots for catalog repositories (all, or the given ones). Server only; runs as the
 * signed-in author/admin (RLS) or the server role. One snapshot per repository per refresh; failures are reported
 * per repository and never stop the others. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { githubConfig, installationToken } from "@/lib/github/app";
import { deliveryFacts } from "@/lib/github/delivery";
import { computeDelivery } from "./delivery";

type Ent = { id: string; key: string; installation_id: number | null; properties: { default_branch?: string } };

export async function refreshDelivery(sb: SupabaseClient, workspaceId: string, userId: string | null, entityIds?: string[]): Promise<{ ok: number; errors: string[] }> {
  const c = githubConfig();
  if (!c.ok) return { ok: 0, errors: ["GitHub App not configured."] };
  let q = sb.from("sf_catalog_entities").select("id, key, installation_id, properties").eq("workspace_id", workspaceId).eq("kind", "repository").eq("archived", false);
  if (entityIds?.length) q = q.in("id", entityIds);
  const { data, error } = await q;
  if (error) return { ok: 0, errors: [error.message] };
  const tokens = new Map<number, Promise<string>>();
  const token = (inst: number) => { if (!tokens.has(inst)) tokens.set(inst, installationToken(c.cfg, inst)); return tokens.get(inst)!; };
  let ok = 0;
  const errors: string[] = [];
  await Promise.all(((data ?? []) as Ent[]).map(async (e) => {
    if (!e.installation_id) return;
    try {
      const f = await deliveryFacts(await token(e.installation_id), { full_name: e.key, default_branch: e.properties.default_branch ?? "main" });
      const now = Date.now();
      const notes = [f.deploysNote, f.truncated ? "More than 500 recent pull requests: the oldest in the 90-day window were not read." : null].filter((x): x is string => !!x);
      const { error: ie } = await sb.from("sf_delivery_snapshots").insert({ workspace_id: workspaceId, entity_id: e.id, computed_by: userId,
        metrics: { d30: computeDelivery(f.prs, f.deploys, 30, now), d90: computeDelivery(f.prs, f.deploys, 90, now) }, notes });
      if (ie) throw new Error(ie.message);
      ok++;
    } catch (err) { errors.push(`${e.key}: ${(err as Error).message}`); }
  }));
  return { ok, errors };
}
