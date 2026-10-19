import { humanName } from "@/lib/names";
import { LocalTime } from "@/components/LocalTime";
import Link from "next/link";
import { notFound } from "next/navigation";
import {requireWorkspace } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { PageHead } from "@/components/PageHead";
import { ActionForm } from "@/components/factory/ActionForm";
import { AgentBuilder } from "@/components/factory/AgentBuilder";
import { newAgentDraft, publishAgentVersion } from "@/app/agentActions";
import { agentCatalog } from "@/lib/factory/agentRun";
import { getAgentBySlug, listAgentVersions, listRecentRunsForVersions } from "@/lib/db/agents";
import { STAGES, SHELVES } from "@/lib/data";

export const dynamic = "force-dynamic";
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) { const { slug } = await params; return { title: `${humanName(slug)} · Playbooks · Skills Factory` }; }

export default async function AgentPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const ctx = await requireWorkspace();
  const agent = await getAgentBySlug(ctx.supabase, ctx.workspace.id, slug);
  if (!agent) notFound();
  const versions = await listAgentVersions(ctx.supabase, agent.id);
  const current = versions.find((x) => String(x.version) === v) ?? versions.find((x) => x.status === "draft") ?? versions[0];
  if (!current) notFound();
  const runs = await listRecentRunsForVersions(ctx.supabase, versions.map((x) => x.id));
  const editable = current.status === "draft" && can(ctx.role, "agent.edit");
  const catalog = [...agentCatalog().values()].sort((x, y) => x.id.localeCompare(y.id));

  return (
    <>
      <PageHead eyebrow="Playbook" title={agent.name} em="" lead={agent.description}
        caption={<span className="chip-group">{versions.map((x) => <Link key={x.id} href={`/agents/${slug}?v=${x.version}`} className="chip" aria-pressed={x.id === current.id}>v{x.version} · {x.status}</Link>)}</span>} />
      <div className="action-row mb-6" style={{ marginTop: 0 }}>
        <Link href={`/agents/${slug}/run?v=${current.version}`} className="btn btn-primary">Run v{current.version}</Link>
        {current.status === "draft" && can(ctx.role, "agent.publish") && <ActionForm action={publishAgentVersion} submit="Publish" submitClass="btn btn-secondary" confirm={`Publish v${current.version}? It becomes frozen and runnable by every member.`} hidden={{ version_id: current.id }} />}
        {current.status !== "draft" && !versions.some((x) => x.status === "draft") && can(ctx.role, "agent.edit") && <ActionForm action={newAgentDraft} submit="Edit as new draft" submitClass="btn btn-secondary" hidden={{ agent_id: agent.id }} />}
        {!editable && current.status === "draft" && <span className="caption">Read-only for your role.</span>}
        {current.status !== "draft" && <span className="caption">v{current.version} is {current.status} and frozen.</span>}
      </div>
      <AgentBuilder key={current.id} initial={current.spec} versionId={current.id} catalog={catalog} stages={[...STAGES, ...SHELVES]} editable={editable} />
      <section className="section">
        <div className="h3 mb-2">Recent runs</div>
        <div className="list">{runs.map((r) => (
          <Link key={r.id} href={`/agent-runs/${r.id}`} className="list-row row-link"><span><LocalTime iso={r.created_at} /> · v{versions.find((x) => x.id === r.agent_version_id)?.version}</span><span>{r.status}{r.cost_usd != null ? ` · ≈$${Number(r.cost_usd).toFixed(4)}` : ""}</span></Link>))}
          {runs.length === 0 && <p className="none">No runs yet.</p>}</div>
      </section>
    </>
  );
}
