import { requireWorkspace } from "@/lib/factory/db";
import { listWorkspaceRuns } from "@/lib/db/runs";
import { PageHead } from "@/components/PageHead";
import { RunsTable, type RunListItem } from "@/components/factory/RunsTable";

export const metadata = { title: "Activity · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function ActivityPage() {
  const ctx = await requireWorkspace();
  const rows = await listWorkspaceRuns(ctx.supabase, ctx.workspace.id);
  const items: RunListItem[] = rows.map((r) => ({ ...r, skill: r.sf_skill_versions.sf_skills.name, slug: r.sf_skill_versions.sf_skills.slug, version: r.sf_skill_versions.version }));
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
