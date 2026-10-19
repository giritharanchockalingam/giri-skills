/* Data access for roles and talent pools (sf_talent) and their versions. Queries run as the signed-in user (RLS applies). */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { TalentRow, TalentVersionRow } from "@/lib/factory/talentData";
import type { RoleSpec, PoolSpec } from "@/lib/factory/talent";

export type TalentKind = "role" | "pool";
export type TalentSummary = Pick<TalentRow, "slug" | "name" | "status">;
export type TalentVersionSummary = Pick<TalentVersionRow<RoleSpec & PoolSpec>, "talent_id" | "version" | "status" | "spec">;
export interface PublishedTalentSpec { skills?: string[]; members?: { role: string }[] }

/** Slug, name and status of every role (or pool) of the workspace. */
export async function listTalentSummaries(sb: SupabaseClient, workspaceId: string, kind: TalentKind): Promise<TalentSummary[] | null> {
  const { data } = await sb.from("sf_talent").select("slug, name, status").eq("workspace_id", workspaceId).eq("kind", kind);
  return data as TalentSummary[] | null;
}

/** The published spec of one workspace role/pool, or null when it has no published version. */
export async function getPublishedTalentSpec(sb: SupabaseClient, workspaceId: string, kind: TalentKind, slug: string): Promise<PublishedTalentSpec | null> {
  const { data } = await sb.from("sf_talent").select("sf_talent_versions(spec, status)").eq("workspace_id", workspaceId).eq("kind", kind).eq("slug", slug).maybeSingle();
  return ((data as { sf_talent_versions?: { spec: PublishedTalentSpec; status: string }[] } | null)?.sf_talent_versions ?? []).find((v) => v.status === "published")?.spec ?? null;
}

export async function getTalentBySlug(sb: SupabaseClient, workspaceId: string, kind: TalentKind, slug: string): Promise<TalentRow | null> {
  const { data } = await sb.from("sf_talent").select("*").eq("workspace_id", workspaceId).eq("kind", kind).eq("slug", slug).maybeSingle();
  return (data ?? null) as TalentRow | null;
}

/** Every version of one role/pool, newest first. */
export async function listTalentVersions(sb: SupabaseClient, talentId: string): Promise<TalentVersionRow<RoleSpec & PoolSpec>[]> {
  const { data } = await sb.from("sf_talent_versions").select("*").eq("talent_id", talentId).order("version", { ascending: false });
  return (data ?? []) as TalentVersionRow<RoleSpec & PoolSpec>[];
}

/** Every role (or pool) of the workspace, most recently updated first. */
export async function listTalent(sb: SupabaseClient, workspaceId: string, kind: TalentKind): Promise<TalentRow[]> {
  const { data } = await sb.from("sf_talent").select("*").eq("workspace_id", workspaceId).eq("kind", kind).order("updated_at", { ascending: false });
  return (data ?? []) as TalentRow[];
}

/** Versions (newest first) of the given roles/pools; no query when there are none. */
export async function listTalentVersionSummaries(sb: SupabaseClient, talentIds: string[]): Promise<TalentVersionSummary[]> {
  if (!talentIds.length) return [];
  const { data } = await sb.from("sf_talent_versions").select("talent_id, version, status, spec").in("talent_id", talentIds).order("version", { ascending: false });
  return (data ?? []) as TalentVersionSummary[];
}
