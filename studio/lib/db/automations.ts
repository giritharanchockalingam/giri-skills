/* Data access for the workflow orchestrator pages (RLS: members read, admins write automations). */
import type { SupabaseClient } from "@supabase/supabase-js";

export interface AutomationView { id: string; name: string; trigger: string; repos: string[]; checks: string[]; report_to_github: boolean; enabled: boolean; created_at: string }
export interface AutomationRunView { id: string; automation_id: string; repo: string; event: string; head_sha: string | null; pr_number: number | null; status: string;
  verdicts: Record<string, { verdict: string; summary: string }>; check_run_url: string | null; error: string | null; started_at: string; finished_at: string | null; entity_id: string | null }

export async function loadAutomations(sb: SupabaseClient, ws: string) {
  const [a, r, e] = await Promise.all([
    sb.from("sf_automations").select("id, name, trigger, repos, checks, report_to_github, enabled, created_at").eq("workspace_id", ws).order("created_at"),
    sb.from("sf_automation_runs").select("id, automation_id, repo, event, head_sha, pr_number, status, verdicts, check_run_url, error, started_at, finished_at, entity_id")
      .eq("workspace_id", ws).order("started_at", { ascending: false }).limit(100),
    sb.from("sf_catalog_entities").select("key").eq("workspace_id", ws).eq("kind", "repository").eq("archived", false).order("key"),
  ]);
  return { automations: (a.data ?? []) as AutomationView[], runs: (r.data ?? []) as AutomationRunView[], repos: (e.data ?? []).map((x) => x.key as string) };
}

export const insertAutomation = (sb: SupabaseClient, row: { workspace_id: string; name: string; trigger: string; repos: string[]; checks: string[]; report_to_github: boolean; created_by: string }) =>
  sb.from("sf_automations").insert(row);
export const setAutomationEnabled = (sb: SupabaseClient, ws: string, id: string, enabled: boolean) =>
  sb.from("sf_automations").update({ enabled }).eq("workspace_id", ws).eq("id", id);
export const deleteAutomation = (sb: SupabaseClient, ws: string, id: string) =>
  sb.from("sf_automations").delete().eq("workspace_id", ws).eq("id", id);
