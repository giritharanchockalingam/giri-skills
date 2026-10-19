import { LocalTime } from "@/components/LocalTime";
import Link from "next/link";
import {requireWorkspace } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { PageHead } from "@/components/PageHead";
import { ActionForm } from "@/components/factory/ActionForm";
import { createAgent } from "@/app/agentActions";
import { listAgentsOverview } from "@/lib/db/agents";
import templates from "@/data/agent-templates.json";

export const metadata = { title: "Agents · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function AgentsPage() {
  const ctx = await requireWorkspace();
  const { agents, versions, runs } = await listAgentsOverview(ctx.supabase, ctx.workspace.id);
  const tpls = templates as unknown as { name: string; spec: { description: string; steps: unknown[] } }[];

  return (
    <>
      <PageHead eyebrow={`Agents · ${ctx.workspace.name}`} title="Agents, configured" em="not coded" after="."
        lead="An agent is a configuration of skills: pick skills, they wire themselves, add approvals where a person decides. Change the configuration and you have a different agent." />
      <div className="stack">
        <div className="card">
          <div className="tablewrap"><table className="tbl"><thead><tr><th>Agent</th><th>Steps</th><th>Version</th><th>Last run</th><th>What it does</th></tr></thead><tbody>
            {agents.map((a) => {
              const vs = versions.filter((v) => v.agent_id === a.id).sort((x, y) => y.version - x.version);
              const latest = vs[0];
              const last = runs.find((r) => vs.some((v) => v.id === r.agent_version_id));
              return (
                <tr key={a.id}>
                  <td><Link href={`/agents/${a.slug}`} className="link"><b>{a.name}</b></Link></td>
                  <td>{latest ? latest.spec.steps.length : 0}</td>
                  <td>{latest ? <>v{latest.version} <span className="caption">{latest.status}</span></> : "—"}</td>
                  <td>{last ? <Link href={`/agent-runs/${last.id}`} className="link">{last.status}</Link> : <span className="none">never</span>} {last && <span className="caption"><LocalTime iso={last.created_at} /></span>}</td>
                  <td className="caption">{a.description}</td>
                </tr>
              );
            })}
            {agents.length === 0 && <tr><td colSpan={5} className="none">No agents yet. Start from a template or a blank canvas.</td></tr>}
          </tbody></table></div>
        </div>
        {can(ctx.role, "agent.edit") && (
          <div className="card card-pad" style={{ maxWidth: 720 }}>
            <div className="h3">New agent</div>
            <ActionForm action={createAgent} submit="Create agent">
              <div className="ab-grid">
                <div className="field"><label htmlFor="na-name">Name</label><input id="na-name" name="name" className="input" required maxLength={160} placeholder="e.g. Pursuit for Acme" /></div>
                <div className="field"><label htmlFor="na-tpl">Start from</label>
                  <select id="na-tpl" name="template" className="select" defaultValue="">
                    <option value="">Blank — pick skills yourself</option>
                    {tpls.map((t) => <option key={t.name} value={t.name}>{t.name} ({t.spec.steps.length} steps)</option>)}
                  </select></div>
              </div>
            </ActionForm>
          </div>
        )}
      </div>
    </>
  );
}
