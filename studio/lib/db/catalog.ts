/* Data access for the catalog (GitHub installations, repositories, syncs, scorecards). Queries run as the signed-in user. */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Applicable, Signal } from "@/lib/github/detect";

export interface InstallationRow { installation_id: number; account_login: string; account_type: string; repository_selection: string; suspended_at: string | null; created_at: string }
export interface SyncRow { status: string; counts: unknown; error: string | null; started_at: string; finished_at: string | null }
export interface LatestScoreRow { entity_id: string; check_id: string; verdict: string; summary: string; created_at: string }
export interface CatalogEntityRow { id: string; key: string; title: string; url: string; owner: string | null; archived: boolean; last_activity_at: string | null;
  properties: { description?: string | null; visibility?: string; stack?: Signal[]; applicable?: Applicable[]; counts?: { files: number; tests: number; migrations: number; workflows: number }; tree_truncated?: boolean } }
export type CatalogEntityDetail = Pick<CatalogEntityRow, "id" | "key" | "url" | "owner" | "properties">;
export interface ScorecardResultRow { id: string; check_id: string; skill: string; verdict: string; summary: string; findings: number | null; commit_sha: string | null; duration_ms: number | null; created_at: string;
  details: { report?: string; log_tail?: string; files_used?: number; partial?: boolean; runtime_status?: string; outputs?: { path: string; sha256: string; bytes: number }[] } }

/** The catalog page: installations, repository entities, the last sync and the latest score per check. */
export async function loadCatalog(sb: SupabaseClient, workspaceId: string): Promise<{ installations: InstallationRow[]; entities: CatalogEntityRow[]; lastSync: SyncRow | null; scores: LatestScoreRow[] }> {
  const [instQ, entQ, syncQ, scoreQ] = await Promise.all([
    sb.from("sf_github_installations").select("installation_id, account_login, account_type, repository_selection, suspended_at, created_at").eq("workspace_id", workspaceId),
    sb.from("sf_catalog_entities").select("id, key, title, url, owner, archived, last_activity_at, properties").eq("workspace_id", workspaceId).eq("kind", "repository").order("last_activity_at", { ascending: false, nullsFirst: false }),
    sb.from("sf_catalog_syncs").select("status, counts, error, started_at, finished_at").eq("workspace_id", workspaceId).order("started_at", { ascending: false }).limit(1),
    sb.from("sf_scorecard_latest").select("entity_id, check_id, verdict, summary, created_at").eq("workspace_id", workspaceId),
  ]);
  return {
    installations: (instQ.data ?? []) as InstallationRow[],
    entities: (entQ.data ?? []) as CatalogEntityRow[],
    lastSync: ((syncQ.data as SyncRow[] | null)?.[0] ?? null),
    scores: (scoreQ.data ?? []) as LatestScoreRow[],
  };
}

export async function getCatalogEntity(sb: SupabaseClient, workspaceId: string, id: string): Promise<CatalogEntityDetail | null> {
  const { data } = await sb.from("sf_catalog_entities").select("id, key, url, owner, properties").eq("workspace_id", workspaceId).eq("id", id).maybeSingle();
  return (data ?? null) as CatalogEntityDetail | null;
}

/** The 200 most recent scorecard results of one entity, newest first. */
export async function listEntityResults(sb: SupabaseClient, workspaceId: string, entityId: string): Promise<ScorecardResultRow[]> {
  const { data } = await sb.from("sf_scorecard_results").select("id, check_id, skill, verdict, summary, findings, commit_sha, duration_ms, created_at, details")
    .eq("workspace_id", workspaceId).eq("entity_id", entityId).order("created_at", { ascending: false }).limit(200);
  return (data ?? []) as ScorecardResultRow[];
}
