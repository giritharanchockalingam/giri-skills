import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { loadCatalog } from "@/lib/db/catalog";
import { listSkillStatuses } from "@/lib/db/skills";
import { listAgentNames } from "@/lib/db/agents";
import { ASSET_LABEL, ASSET_PLURAL, type AiAsset, type AssetKind } from "@/lib/github/assets";

export const metadata = { title: "AI assets · Skills Factory" };
export const dynamic = "force-dynamic";

const ORDER: AssetKind[] = ["agent", "mcp_server", "skill", "mcp_config", "agent_instructions"];
const LEAD: Record<AssetKind, string> = {
  agent: "Agent frameworks in use (proved by a dependency) and agent definition files.",
  mcp_server: "MCP servers these repositories expose (the MCP SDK as a dependency, or an MCP endpoint route).",
  skill: "Agent Skills (SKILL.md folders) kept in these repositories.",
  mcp_config: "MCP client configs: the servers these repositories' agents or IDEs connect to.",
  agent_instructions: "Files coding agents read and follow in these repositories.",
};

/** AI agent management (Port-style): every agent, MCP server and skill found in the catalog's repositories, plus what
 *  this portal itself defines and serves — each with the file or record that proves it. */
export default async function AiAssetsPage({ searchParams }: { searchParams: Promise<{ kind?: string }> }) {
  const sp = await searchParams;
  const ctx = await requireWorkspace();
  const [catalog, skills, playbooks] = await Promise.all([
    loadCatalog(ctx.supabase, ctx.workspace.id),
    listSkillStatuses(ctx.supabase, ctx.workspace.id),
    listAgentNames(ctx.supabase, ctx.workspace.id),
  ]);
  const repos = catalog.entities.filter((e) => !e.archived);
  const found: (AiAsset & { repo: string; repoId: string; url: string })[] = repos.flatMap((e) => (e.properties.ai_assets ?? []).map((a) => ({ ...a, repo: e.key, repoId: e.id, url: e.url })));
  const scanned = repos.filter((e) => Array.isArray(e.properties.ai_assets)).length;
  const kind = ORDER.includes(sp.kind as AssetKind) ? (sp.kind as AssetKind) : null;
  const count = (k: AssetKind) => found.filter((a) => a.kind === k).length;
  const sk = skills ?? [];
  const published = sk.filter((s) => s.status === "published");
  const pb = playbooks;

  return (
    <>
      <PageHead eyebrow="Platform · AI assets" title="Every agent, server and" em="skill" after="."
        lead="What your repositories contain — agents, MCP servers, skills, MCP configs and agent instructions, each with the file that proves it — next to what this portal defines and serves." />
      <p className="caption mb-4"><Link className="link" href="/catalog">Repositories</Link> · {scanned} of {repos.length} repositor{repos.length === 1 ? "y" : "ies"} scanned{scanned < repos.length ? " — sync the catalog to scan the rest" : ""}.</p>

      <div className="cat-tiles mb-4">
        {ORDER.map((k) => <Link key={k} href={kind === k ? "/ai-assets" : `/ai-assets?kind=${k}`} className={`cat-tile${kind === k ? " cat-tile-on" : ""}`}><b>{count(k)}</b><span>{count(k) === 1 ? ASSET_LABEL[k] : ASSET_PLURAL[k]} in repositories</span></Link>)}
        <Link href="/playbooks" className="cat-tile"><b>{pb.length}</b><span>playbooks defined here</span></Link>
        <Link href="/connect" className="cat-tile"><b>{published.length}</b><span>skills published here, callable over MCP</span></Link>
      </div>

      {ORDER.filter((k) => !kind || k === kind).map((k) => {
        const rows = found.filter((a) => a.kind === k);
        if (!rows.length) return null;
        return (
          <section key={k} className="section">
            <div className="h3">{ASSET_PLURAL[k]} <span className="caption">({rows.length})</span></div>
            <p className="caption">{LEAD[k]}</p>
            <div className="card"><div className="tablewrap"><table className="mini cat-table">
              <thead><tr><th>Name</th><th>Repository</th><th>Where</th><th>Evidence</th></tr></thead>
              <tbody>{rows.slice(0, kind ? 500 : 25).map((a) => (
                <tr key={`${a.repo}:${a.kind}:${a.path}:${a.name}`}>
                  <td><b>{a.name}</b><div className="caption">{a.detail}</div></td>
                  <td><Link className="link" href={`/catalog/${a.repoId}`}>{a.repo}</Link></td>
                  <td>{a.path === "." ? <span className="caption">repository</span> : <a className="link caption" href={`${a.url}/tree/HEAD/${a.path}`} target="_blank" rel="noreferrer"><code>{a.path}</code></a>}</td>
                  <td className="caption">{a.evidence.map((x) => <code key={x} style={{ marginRight: 6 }}>{x}</code>)}</td>
                </tr>))}</tbody>
            </table></div></div>
            {!kind && rows.length > 25 && <p className="caption"><Link className="link" href={`/ai-assets?kind=${k}`}>All {rows.length} {ASSET_PLURAL[k].toLowerCase()}</Link></p>}
          </section>);
      })}
      {found.length === 0 && <section className="card card-pad"><p className="none" style={{ margin: 0 }}>{scanned ? "No AI assets found in the scanned repositories." : "Not scanned yet — sync the catalog."}</p></section>}

      <section className="section">
        <div className="h3">Defined and served by this portal</div>
        <ul className="ini-repos">
          <li><Link className="link" href="/playbooks">{pb.length} playbook{pb.length === 1 ? "" : "s"}</Link> <span className="caption">— skills chained into playbooks, with approval gates</span></li>
          <li><Link className="link" href="/connect">MCP server /api/mcp</Link> <span className="caption">— {published.length} published skill{published.length === 1 ? "" : "s"}, plus per-role, per-team and per-stage scopes</span></li>
          <li><Link className="link" href="/pipeline">{sk.length} workspace skill{sk.length === 1 ? "" : "s"}</Link> <span className="caption">— {published.length} published</span></li>
        </ul>
      </section>
    </>
  );
}
