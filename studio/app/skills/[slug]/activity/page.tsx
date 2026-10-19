import { loadSkillPage } from "@/lib/factory/skillPage";
import { VersionBar } from "@/components/factory/VersionBar";
import { RunsTable, type RunListItem } from "@/components/factory/RunsTable";
import { listVersionRuns } from "@/lib/db/runs";

export const dynamic = "force-dynamic";

export default async function SkillActivityPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const runs = await listVersionRuns(d.ctx.supabase, d.version.id);
  const items: RunListItem[] = runs.map((r) => ({ ...r, skill: d.skill.name, slug, version: d.version.version }));
  return (
    <>
      <VersionBar slug={slug} view="activity" versions={d.versions} current={d.version} />
      <RunsTable items={items} caption={`Runs of v${d.version.version} (newest first, up to 200).`} />
    </>
  );
}
