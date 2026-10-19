/* Data access for skill runs (sf_runs). Queries run as the signed-in user (RLS applies). */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { RunRow, VersionRow } from "@/lib/factory/db";

type RunListFields = "id" | "status" | "source" | "created_at" | "duration_ms" | "provider" | "model" | "cost_usd" | "cost_is_estimate" | "error";
export type RunListRow = Pick<RunRow, RunListFields>;
export type WorkspaceRunRow = RunListRow & { sf_skill_versions: Pick<VersionRow, "version"> & { sf_skills: { slug: string; name: string } } };
export type RunWithVersion = RunRow & { sf_skill_versions: Pick<VersionRow, "version" | "status" | "manifest_hash"> & { sf_skills: { slug: string; name: string } } };
export type LastRun = Pick<RunRow, "id" | "status" | "created_at">;

/** The 300 most recent runs of the workspace, with each run's skill and version. */
export async function listWorkspaceRuns(sb: SupabaseClient, workspaceId: string): Promise<WorkspaceRunRow[]> {
  const { data } = await sb.from("sf_runs").select("id, status, source, created_at, duration_ms, provider, model, cost_usd, cost_is_estimate, error, sf_skill_versions(version, sf_skills!sf_skill_versions_skill_id_fkey(slug, name))").eq("workspace_id", workspaceId).order("created_at", { ascending: false }).limit(300);
  return (data ?? []) as unknown as WorkspaceRunRow[];
}

/** One run of the workspace with its version and skill, or null. */
export async function getRunWithVersion(sb: SupabaseClient, workspaceId: string, id: string): Promise<RunWithVersion | null> {
  const { data } = await sb.from("sf_runs").select("*, sf_skill_versions(version, status, manifest_hash, sf_skills!sf_skill_versions_skill_id_fkey(slug, name))").eq("id", id).eq("workspace_id", workspaceId).maybeSingle();
  return (data ?? null) as RunWithVersion | null;
}

/** The 200 most recent runs of one version. */
export async function listVersionRuns(sb: SupabaseClient, versionId: string): Promise<RunListRow[]> {
  const { data } = await sb.from("sf_runs").select("id, status, source, created_at, duration_ms, provider, model, cost_usd, cost_is_estimate, error, version_id").eq("version_id", versionId).order("created_at", { ascending: false }).limit(200);
  return (data ?? []) as RunListRow[];
}

/** The most recent run of one version, or null. */
export async function getLastVersionRun(sb: SupabaseClient, versionId: string): Promise<LastRun | null> {
  const { data } = await sb.from("sf_runs").select("id, status, created_at").eq("version_id", versionId).order("created_at", { ascending: false }).limit(1).maybeSingle();
  return (data ?? null) as LastRun | null;
}
