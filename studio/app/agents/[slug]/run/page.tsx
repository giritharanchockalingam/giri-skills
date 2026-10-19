import { notFound } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { AgentRunForm } from "@/components/factory/AgentRunForm";
import type { AgentRow, AgentVersionRow } from "@/lib/factory/agentRun";
import templates from "@/data/agent-templates.json";
import skillDemos from "@/data/skill-demos.json";
import { exampleInputs, type DemoValue } from "@/lib/factory/agents";

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
  // example inputs (fictional fixtures, labelled in each file): templates first, then each step's own skill example
  const demo = exampleInputs(version.spec, templates as unknown as { demo: Record<string, DemoValue> }[], skillDemos as unknown as Record<string, Record<string, DemoValue>>);
  return (
    <>
      <PageHead eyebrow={`Agents · ${slug} · v${version.version}`} title="Run" em={(a as AgentRow).name} after="." lead="Supply the inputs. Steps run on the server one after another; each is checked; approvals pause the run for a reviewer." />
      <AgentRunForm versionId={version.id} inputs={version.spec.inputs} demo={demo} />
    </>
  );
}
