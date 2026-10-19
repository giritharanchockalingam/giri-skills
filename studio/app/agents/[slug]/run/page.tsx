import { notFound } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { AgentRunForm } from "@/components/factory/AgentRunForm";
import { getAgentBySlug, listAgentVersions } from "@/lib/db/agents";
import templates from "@/data/agent-templates.json";
import skillDemos from "@/data/skill-demos.json";
import { exampleInputs, type DemoValue } from "@/lib/factory/agents";

export const dynamic = "force-dynamic";

export default async function RunAgentPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const ctx = await requireWorkspace();
  const a = await getAgentBySlug(ctx.supabase, ctx.workspace.id, slug);
  if (!a) notFound();
  const versions = await listAgentVersions(ctx.supabase, a.id);
  const version = versions.find((x) => String(x.version) === v) ?? versions.find((x) => x.status === "published") ?? versions[0];
  if (!version) notFound();
  // example inputs (fictional fixtures, labelled in each file): templates first, then each step's own skill example
  const demo = exampleInputs(version.spec, templates as unknown as { demo: Record<string, DemoValue> }[], skillDemos as unknown as Record<string, Record<string, DemoValue>>);
  return (
    <>
      <PageHead eyebrow={`Playbook · v${version.version}`} title="Run" em={a.name} after="." lead="Supply the inputs. Steps run on the server one after another; each is checked; approvals pause the run for a reviewer." />
      <AgentRunForm versionId={version.id} inputs={version.spec.inputs} demo={demo} />
    </>
  );
}
