/* Reads of sf_skill_uses (RLS: workspace members). */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { SkillUseRow } from "@/lib/factory/uses";

export async function listVersionUses(sb: SupabaseClient, versionId: string, limit = 50): Promise<SkillUseRow[]> {
  const { data, error } = await sb.from("sf_skill_uses").select("id, created_at, event, integrity, currency").eq("version_id", versionId).order("created_at", { ascending: false }).limit(limit);
  if (error) return [];   // the table arrives with migration 0026; before it is applied the page shows no uses
  return (data ?? []) as SkillUseRow[];
}
