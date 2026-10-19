import { notFound } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { AgentRunForm } from "@/components/factory/AgentRunForm";
import type { AgentRow, AgentVersionRow } from "@/lib/factory/agentRun";
import templates from "@/data/agent-templates.json";

export const dynamic = "force-dynamic";

export default async function RunAgentPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const ctx = await requireWorkspace();
  const { data: a } = await ctx.supabase.from("sf_agents").select("*").eq("workspace_id", ctx.workspace.id).eq("slug", slug).maybeSingle();
  if (!a) notFound();
  const { data: vs } = await ctx.supabase.from("sf_agent_versions").select("*").eq("agent_id", (a as AgentRow).id).order("version", { ascending: false });
  const versions = (vs ?? []) as AgentVersionRow[];
  const version = versions.find((x) => String(x.version) === v) ?? versions.find((x) => x.status === "published") ?? versions[0];
  if (!version) notFound();
  // demo inputs from shipped templates (fictional fixtures, labelled in each file)
  const tpls = templates as unknown as { name: string; demo: Record<string, { kind: "text"; content: string; ext: string; source?: string } | { kind: "value"; value: string }> }[];
  // the template covering the most of this agent's inputs; a tailored agent still gets demo values for the inputs it shares
  const names = version.spec.inputs.map((i) => i.name);
  const best = tpls.map((t) => ({ t, n: names.filter((n) => n in t.demo).length })).sort((a, b) => b.n - a.n)[0];
  const demo = best && best.n > 0 ? Object.fromEntries(Object.entries(best.t.demo).filter(([k]) => names.includes(k))) as typeof best.t.demo : null;
  return (
    <>
      <PageHead eyebrow={`Agents · ${slug} · v${version.version}`} title="Run" em={(a as AgentRow).name} after="." lead="Supply the inputs. Steps run on the server one after another; each is checked; approvals pause the run for a reviewer." />
      <AgentRunForm versionId={version.id} inputs={version.spec.inputs} demo={demo} />
    </>
  );
}
