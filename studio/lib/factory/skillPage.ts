/* Loader shared by the skill detail layout and its sub-views (deduplicated per request with React cache). Server only. */
import { cache } from "react";
import { notFound } from "next/navigation";
import { requireWorkspace, getSkillBySlug, pickVersion, type WsCtx, type SkillRow, type VersionRow, type ReleaseStateRow } from "./db";

export interface SkillPageData {
  ctx: WsCtx; skill: SkillRow; versions: VersionRow[]; states: ReleaseStateRow[];
  version: VersionRow; state: ReleaseStateRow | null; published: VersionRow | null; runCount: number;
}

export const loadSkillPage = cache(async (slug: string, wanted?: string | null): Promise<SkillPageData> => {
  const ctx = await requireWorkspace();
  const data = await getSkillBySlug(ctx, slug);
  if (!data) notFound();
  const version = pickVersion(data.versions, wanted);
  if (!version) notFound();
  const state = data.states.find((s) => s.version_id === version.id) ?? null;
  const published = data.versions.find((v) => v.status === "published") ?? null;
  const { count } = await ctx.supabase.from("sf_runs").select("id", { count: "exact", head: true }).eq("version_id", version.id);
  return { ctx, ...data, version, state, published, runCount: count ?? 0 };
});

export const versionQuery = (v: VersionRow) => `?v=${v.version}`;
