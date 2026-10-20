import { skillTitle } from "@/lib/names";
import { requireWorkspace } from "@/lib/factory/db";
import { listWorkspaceRuns } from "@/lib/db/runs";
import { PageHead } from "@/components/PageHead";
import { RunsTable, type RunListItem } from "@/components/factory/RunsTable";

export const metadata = { title: "Activity · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function ActivityPage() {
  const ctx = await requireWorkspace();
  const rows = await listWorkspaceRuns(ctx.supabase, ctx.workspace.id);
  const items: RunListItem[] = rows.map((r) => ({ ...r, skill: skillTitle(r.sf_skill_versions.sf_skills.name), slug: r.sf_skill_versions.sf_skills.slug, version: r.sf_skill_versions.version }));
  const failed = items.filter((r) => r.status === "failed" || r.status === "timeout").length;
  return (
    <>
      <PageHead eyebrow={`Skills · runs · ${ctx.workspace.name}`} title="Every server run," em="recorded" after="."
        lead={items.length ? `${items.length} most recent runs; ${failed} failed or timed out. Open a run for its steps, checks, outputs, logs and usage.` : "No runs yet. Test a skill, run an evaluation, or call the API and the record appears here."}
        caption="Server runs: portal, API, MCP and playbook steps. Runs in the browser are counted on Insights (runs = server + browser). Each run references the exact version (manifest hash) it executed; costs are estimates from provider-reported tokens." />
      <RunsTable items={items} caption="newest first, up to 300" showSkill />
    </>
  );
}
