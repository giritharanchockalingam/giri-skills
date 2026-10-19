/* Data access for initiatives. Progress is computed from the live scorecard by the caller (lib/scorecards/levels.ts). */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Level } from "@/lib/scorecards/levels";

export interface InitiativeRow { id: string; title: string; description: string; target_level: Level; repos: string[]; owner: string; due_on: string; status: "active" | "closed"; created_at: string }
export interface NewInitiative { workspace_id: string; title: string; description: string; target_level: Level; repos: string[]; owner: string; due_on: string; created_by: string }

export async function listInitiatives(sb: SupabaseClient, workspaceId: string): Promise<InitiativeRow[]> {
  const { data } = await sb.from("sf_initiatives").select("id, title, description, target_level, repos, owner, due_on, status, created_at")
    .eq("workspace_id", workspaceId).order("status", { ascending: true }).order("due_on", { ascending: true });
  return (data ?? []) as InitiativeRow[];
}

export const insertInitiative = (sb: SupabaseClient, row: NewInitiative) => sb.from("sf_initiatives").insert(row);
export const setInitiativeStatus = (sb: SupabaseClient, workspaceId: string, id: string, status: "active" | "closed") =>
  sb.from("sf_initiatives").update({ status }).eq("workspace_id", workspaceId).eq("id", id);
export const deleteInitiative = (sb: SupabaseClient, workspaceId: string, id: string) =>
  sb.from("sf_initiatives").delete().eq("workspace_id", workspaceId).eq("id", id);
