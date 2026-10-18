import { requireWorkspace, type RunRow, type VersionRow } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { RunsTable, type RunListItem } from "@/components/factory/RunsTable";

export const metadata = { title: "Activity · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function ActivityPage() {
  const ctx = await requireWorkspace();
  const { data } = await ctx.supabase.from("sf_runs").select("id, status, source, created_at, duration_ms, provider, model, cost_usd, cost_is_estimate, error, sf_skill_versions(version, sf_skills!sf_skill_versions_skill_id_fkey(slug, name))").eq("workspace_id", ctx.workspace.id).order("created_at", { ascending: false }).limit(300);
  type Row = Pick<RunRow, "id" | "status" | "source" | "created_at" | "duration_ms" | "provider" | "model" | "cost_usd" | "cost_is_estimate" | "error"> & { sf_skill_versions: Pick<VersionRow, "version"> & { sf_skills: { slug: string; name: string } } };
  const items: RunListItem[] = ((data ?? []) as unknown as Row[]).map((r) => ({ ...r, skill: r.sf_skill_versions.sf_skills.name, slug: r.sf_skill_versions.sf_skills.slug, version: r.sf_skill_versions.version }));
  const failed = items.filter((r) => r.status === "failed" || r.status === "timeout").length;
  return (
    <>
      <PageHead eyebrow={`Activity · ${ctx.workspace.name}`} title="Every run," em="recorded" after="."
        lead={items.length ? `${items.length} most recent runs; ${failed} failed or timed out. Open a run for its steps, checks, outputs, logs and usage.` : "No runs yet. Test a skill, run an evaluation, or call the API and the record appears here."}
        caption="Each run references the exact version (manifest hash) it executed. Costs are estimates derived from provider-reported tokens; measured values are never invented." />
      <RunsTable items={items} caption="newest first, up to 300" showSkill />
    </>
  );
}
