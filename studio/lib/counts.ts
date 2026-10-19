/* The skill counts, defined once. Every page that states how many skills there are uses this sentence, so the numbers
 * always reconcile: library (shipped, runnable) · reference (vendored, read-only) · in this workspace (imported), of which
 * published (live over MCP/API) and in progress. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { skills as librarySkills } from "@/lib/data";
import upstream from "@/data/upstream.json";

import type { SkillCounts } from "./countsText";
export { countsSentence, type SkillCounts } from "./countsText";

export async function skillCounts(sb: SupabaseClient, ws: string): Promise<SkillCounts> {
  const { data } = await sb.from("sf_skills").select("status").eq("workspace_id", ws);
  const rows = (data ?? []) as { status: string }[];
  const published = rows.filter((r) => r.status === "published").length;
  const live = rows.filter((r) => r.status !== "retired").length;
  return { library: librarySkills.length, reference: (upstream as unknown[]).length, workspace: live, published, inProgress: live - published };
}

