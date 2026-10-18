import { loadSkillPage } from "@/lib/factory/skillPage";
import { VersionBar } from "@/components/factory/VersionBar";
import { RunsTable, type RunListItem } from "@/components/factory/RunsTable";
import type { RunRow } from "@/lib/factory/db";

export const dynamic = "force-dynamic";

export default async function SkillActivityPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const { data } = await d.ctx.supabase.from("sf_runs").select("id, status, source, created_at, duration_ms, provider, model, cost_usd, cost_is_estimate, error, version_id").eq("version_id", d.version.id).order("created_at", { ascending: false }).limit(200);
  const items: RunListItem[] = ((data ?? []) as Pick<RunRow, "id" | "status" | "source" | "created_at" | "duration_ms" | "provider" | "model" | "cost_usd" | "cost_is_estimate" | "error">[]).map((r) => ({ ...r, skill: d.skill.name, slug, version: d.version.version }));
  return (
    <>
      <VersionBar slug={slug} view="activity" versions={d.versions} current={d.version} />
      <RunsTable items={items} caption={`Runs of v${d.version.version} (newest first, up to 200).`} />
    </>
  );
}
