/* Data access for catalog entities of every kind and the relations between them (RLS-scoped). */
import type { SupabaseClient } from "@supabase/supabase-js";

export type Kind = "repository" | "service" | "database";
export interface EntityRow { id: string; kind: Kind; source: string; key: string; title: string; url: string; owner: string | null; archived: boolean; last_activity_at: string | null; properties: Record<string, unknown> }
export interface RelatedRow { relation: string; direction: "out" | "in"; evidence: string; other: Pick<EntityRow, "id" | "kind" | "key" | "title" | "url"> }
export interface SyncLogRow { provider: string; status: string; counts: Record<string, number>; error: string | null; started_at: string; finished_at: string | null }

const COLS = "id, kind, source, key, title, url, owner, archived, last_activity_at, properties";

export async function listEntities(sb: SupabaseClient, ws: string, kind: Kind): Promise<EntityRow[]> {
  const { data } = await sb.from("sf_catalog_entities").select(COLS).eq("workspace_id", ws).eq("kind", kind).eq("archived", false).order("last_activity_at", { ascending: false, nullsFirst: false });
  return (data ?? []) as EntityRow[];
}
export async function getEntity(sb: SupabaseClient, ws: string, id: string): Promise<EntityRow | null> {
  const { data } = await sb.from("sf_catalog_entities").select(COLS).eq("workspace_id", ws).eq("id", id).maybeSingle();
  return (data ?? null) as EntityRow | null;
}

/** Every relation of the workspace, with both ends resolved (one query each, joined here). */
export async function allRelations(sb: SupabaseClient, ws: string): Promise<{ from: string; to: string; type: string; evidence: string }[]> {
  const { data } = await sb.from("sf_catalog_relations").select("from_id, to_id, type, evidence").eq("workspace_id", ws);
  return ((data ?? []) as { from_id: string; to_id: string; type: string; evidence: string }[]).map((r) => ({ from: r.from_id, to: r.to_id, type: r.type, evidence: r.evidence }));
}

export async function relationsOf(sb: SupabaseClient, ws: string, id: string): Promise<RelatedRow[]> {
  const [out, inn] = await Promise.all([
    sb.from("sf_catalog_relations").select("type, evidence, other:sf_catalog_entities!sf_catalog_relations_to_id_fkey(id, kind, key, title, url)").eq("workspace_id", ws).eq("from_id", id),
    sb.from("sf_catalog_relations").select("type, evidence, other:sf_catalog_entities!sf_catalog_relations_from_id_fkey(id, kind, key, title, url)").eq("workspace_id", ws).eq("to_id", id),
  ]);
  type R = { type: string; evidence: string; other: RelatedRow["other"] };
  return [...((out.data ?? []) as unknown as R[]).map((r) => ({ relation: r.type, direction: "out" as const, evidence: r.evidence, other: r.other })),
    ...((inn.data ?? []) as unknown as R[]).map((r) => ({ relation: r.type, direction: "in" as const, evidence: r.evidence, other: r.other }))];
}

export async function lastSyncs(sb: SupabaseClient, ws: string): Promise<Record<string, SyncLogRow | null>> {
  const { data } = await sb.from("sf_catalog_syncs").select("provider, status, counts, error, started_at, finished_at").eq("workspace_id", ws).order("started_at", { ascending: false }).limit(60);
  const out: Record<string, SyncLogRow | null> = { github: null, vercel: null, supabase: null };
  for (const r of (data ?? []) as SyncLogRow[]) if (!out[r.provider]) out[r.provider] = r;
  return out;
}

/** How a relation reads from one end ("Built from", "Deployed as", "Uses database", "Used by"). */
export const RELATION_LABEL: Record<string, { out: string; in: string }> = {
  built_from: { out: "Built from", in: "Deployed as" },
  uses_database: { out: "Uses database", in: "Used by" },
};
