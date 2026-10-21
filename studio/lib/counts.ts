/* The skill counts, defined once. Every page that states how many skills there are uses this sentence, so the numbers
 * always reconcile: library (shipped, runnable) · reference (vendored, read-only) · in this workspace (imported), of which
 * published (live over MCP/API) and in progress. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { skills as librarySkills } from "@/lib/data";
import upstream from "@/data/upstream.json";

import type { SkillCounts } from "./countsText";
export { countsSentence, countsBridge, type SkillCounts } from "./countsText";

export async function skillCounts(sb: SupabaseClient, ws: string): Promise<SkillCounts> {
  const { data } = await sb.from("sf_skills").select("id, status").eq("workspace_id", ws);
  const rows = (data ?? []) as { id: string; status: string }[];
  const published = rows.filter((r) => r.status === "published").length;
  const liveRows = rows.filter((r) => r.status !== "retired");
  const live = liveRows.length;
  const ids = liveRows.map((r) => r.id);
  const { data: vs } = ids.length ? await sb.from("sf_skill_versions").select("skill_id, source").in("skill_id", ids) : { data: [] };
  const repoOf = new Map<string, string>();
  for (const v of (vs ?? []) as { skill_id: string; source: { kind?: string; repo_skill?: string } }[]) if (v.source?.kind === "repo" && v.source.repo_skill) repoOf.set(v.skill_id, v.source.repo_skill);
  const libIds = new Set(librarySkills.map((s) => s.id));
  const imported = new Set([...repoOf.values()].filter((r) => libIds.has(r))).size;
  return { library: librarySkills.length, reference: (upstream as unknown[]).length, workspace: live, published, inProgress: live - published,
    imported, notImported: librarySkills.length - imported, authored: ids.filter((id) => !repoOf.has(id)).length };
}

