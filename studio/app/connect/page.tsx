import Link from "next/link";
import { loadFunnel } from "@/lib/db/skills";
import { headers } from "next/headers";
import { requireWorkspace } from "@/lib/factory/db";
import { listTalentSummaries, getPublishedTalentSpec } from "@/lib/db/talent";
import { listSkillStatuses } from "@/lib/db/skills";
import { PageHead } from "@/components/PageHead";
import { CopyButton } from "@/components/CopyButton";
import { ROLE_TEMPLATES, POOL_TEMPLATES } from "@/lib/factory/talentData";
import { skills as repoSkills, STAGES } from "@/lib/data";
import { humanName } from "@/lib/names";

export const metadata = { title: "Connect · Skills Factory" };
export const dynamic = "force-dynamic";

type Kind = "workspace" | "role" | "team" | "stage";
type Lib = { id: string; card?: string; stage?: string | string[] | null };
const LIB = repoSkills as unknown as Lib[];

/** Connect a workspace, role, team or lifecycle stage to Claude Code, Claude Desktop, Cursor or VS Code as an MCP server. */
export default async function ConnectPage({ searchParams }: { searchParams: Promise<{ kind?: string; slug?: string }> }) {
  const sp = await searchParams;
  const ctx = await requireWorkspace();
  const h = await headers();
  const origin = `${h.get("x-forwarded-proto") ?? "https"}://${h.get("x-forwarded-host") ?? h.get("host")}`;
  const kind: Kind = (["role", "team", "stage"] as const).includes(sp.kind as never) ? (sp.kind as Kind) : "workspace";
  const funnel = await loadFunnel(ctx.supabase, ctx.workspace.id);
  const [wsRoles, wsTeams, published] = await Promise.all([
    listTalentSummaries(ctx.supabase, ctx.workspace.id, "role"),
    listTalentSummaries(ctx.supabase, ctx.workspace.id, "pool"),
    listSkillStatuses(ctx.supabase, ctx.workspace.id),
  ]);
  const roleList = [...new Map([...ROLE_TEMPLATES.map((r) => [r.name, r.title] as const), ...(wsRoles ?? []).filter((r) => r.status === "published").map((r) => [r.slug, `${r.name} (yours)`] as const)]).entries()];
  const teamList = [...new Map([...POOL_TEMPLATES.map((p) => [p.name, p.title] as const), ...(wsTeams ?? []).filter((r) => r.status === "published").map((r) => [r.slug, `${r.name} (yours)`] as const)]).entries()];
  const options: Record<Kind, [string, string][]> = { workspace: [], role: roleList, team: teamList, stage: STAGES.map((s) => [s.id, `${s.n}. ${s.name}`]) };
  const slug = kind === "workspace" ? null : options[kind].some(([s]) => s === sp.slug) ? sp.slug! : options[kind][0]?.[0] ?? null;
  const path = kind === "workspace" ? "/api/mcp" : `/api/mcp/${kind}/${slug}`;
  const url = `${origin}${path}`;
  const name = `skills-${kind === "workspace" ? "workspace" : slug}`.slice(0, 40);

  // what this server will offer: the library skills in scope, and which of them this workspace has published
  // a published, tailored role/team of this workspace wins over the template of the same name (same rule as the server)
  const mine = async (k: "role" | "pool") => {
    const t = (k === "role" ? wsRoles : wsTeams)?.find((r) => r.slug === slug && r.status === "published");
    if (!t) return null;
    return getPublishedTalentSpec(ctx.supabase, ctx.workspace.id, k, slug!);
  };
  const myRole = kind === "role" ? await mine("role") : null;
  const tpl = kind === "role" ? (myRole?.skills ? { skills: myRole.skills } : ROLE_TEMPLATES.find((r) => r.name === slug)) : null;
  const myTeam = kind === "team" ? await mine("pool") : null;
  const team = kind === "team" ? (myTeam?.members ? { members: myTeam.members } : POOL_TEMPLATES.find((p) => p.name === slug)) : null;
  const inScope = kind === "workspace" ? null : new Set(
    kind === "stage" ? LIB.filter((s) => (Array.isArray(s.stage) ? s.stage.includes(slug!) : s.stage === slug)).map((s) => s.id)
      : kind === "role" ? tpl?.skills ?? []
      : (team?.members ?? []).flatMap((m) => ROLE_TEMPLATES.find((r) => r.name === m.role)?.skills ?? []));
  const pubBySlug = new Map((published ?? []).map((s) => [s.slug, s.status]));
  const rows = (inScope ? [...inScope] : LIB.map((s) => s.id).filter((id) => pubBySlug.has(id.split("/")[1])))
    .map((id) => ({ id, name: humanName(id.split("/")[1]), card: LIB.find((s) => s.id === id)?.card ?? "", status: pubBySlug.get(id.split("/")[1]) ?? "not added" }))
    .sort((a, b) => Number(b.status === "published") - Number(a.status === "published") || a.name.localeCompare(b.name));
  const live = rows.filter((r) => r.status === "published").length;

  const snippets: { client: string; where: string; text: string }[] = [
    { client: "Claude Code", where: "Run once in a terminal (SF_API_KEY holds your key)",
      text: `claude mcp add --transport http ${name} ${url} \\\n  --header "Authorization: Bearer $SF_API_KEY"` },
    { client: "Cursor", where: "~/.cursor/mcp.json (or .cursor/mcp.json in a project)",
      text: JSON.stringify({ mcpServers: { [name]: { url, headers: { Authorization: "Bearer ${env:SF_API_KEY}" } } } }, null, 2) },
    { client: "VS Code", where: ".vscode/mcp.json — VS Code asks for the key once and stores it securely",
      text: JSON.stringify({ inputs: [{ type: "promptString", id: "sf-key", description: "Skills Factory API key", password: true }], servers: { [name]: { type: "http", url, headers: { Authorization: "Bearer ${input:sf-key}" } } } }, null, 2) },
    { client: "Claude Desktop", where: "claude_desktop_config.json (bridges with mcp-remote; needs Node.js)",
      text: JSON.stringify({ mcpServers: { [name]: { command: "npx", args: ["-y", "mcp-remote", url, "--header", "Authorization:${SF_AUTH}"], env: { SF_AUTH: "Bearer sf_live_…your key…" } } } }, null, 2) },
    { client: "Check it works", where: "Lists the tools this server offers",
      text: `curl -s ${url} -H "Authorization: Bearer $SF_API_KEY" -H "Content-Type: application/json" \\\n  -H "Accept: application/json, text/event-stream" \\\n  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'` },
  ];
  const link = (k: Kind, s?: string) => `/connect?kind=${k}${s ? `&slug=${s}` : ""}`;

  return (
    <>
      <PageHead eyebrow="Connect" title="Use these skills from" em="your tools" after="."
        note={<Link href="/connect/api" className="link-flame">HTTP API reference →</Link>}
        lead="Every workspace, role, team and lifecycle stage is an MCP server. Connect it to Claude Code, Claude Desktop, Cursor or VS Code and its skills become tools — running the published, tested version, within your workspace's limits, with every run recorded." />

      <section className="card card-pad mb-6">
        <div className="h3" style={{ marginTop: 0 }}>1 · What to connect</div>
        <div className="lc-seg" role="tablist" aria-label="Server scope" style={{ marginTop: 8 }}>
          {(["workspace", "role", "team", "stage"] as Kind[]).map((k) => (
            <Link key={k} href={link(k)} role="tab" aria-selected={k === kind} className={`lc-seg-link${k === kind ? " on" : ""}`}>{k === "workspace" ? "Whole workspace" : k === "team" ? "A team" : k === "role" ? "A role" : "A lifecycle stage"}</Link>
          ))}
        </div>
        {kind !== "workspace" && (
          <form method="get" className="flex flex-wrap items-center gap-2 mt-4">
            <input type="hidden" name="kind" value={kind} />
            <select name="slug" className="select" defaultValue={slug ?? ""} style={{ width: "auto" }} aria-label={kind}>
              {options[kind].map(([s, t]) => <option key={s} value={s}>{t}</option>)}
            </select>
            <button type="submit" className="btn btn-secondary btn-sm">Show</button>
          </form>
        )}
        <p className="mt-4" style={{ marginBottom: 0 }}><b>{live}</b> tool{live === 1 ? "" : "s"} live on this server{rows.length > live ? <span className="caption"> · {rows.length - live} more skill{rows.length - live === 1 ? "" : "s"} in scope become tools once published</span> : null}</p>
        {rows.length > live && (
          <div className="mt-3">
            <div className="hero-actions">
              {funnel.some((f) => f.gate === "ready") && <Link className="btn btn-primary btn-sm" href="/pipeline?gate=ready">Publish the {funnel.filter((f) => f.gate === "ready").length} ready</Link>}
              <span className="caption">Only tested, approved versions become tools here. Skill owners publish them in the <Link className="link" href="/pipeline">publish pipeline</Link>.</span>
            </div>
          </div>)}
        <div className="connect-url mt-2"><code>{url}</code> <CopyButton text={url} /></div>
      </section>

      <section className="card card-pad mb-6">
        <div className="h3" style={{ marginTop: 0 }}>2 · Your key</div>
        <p style={{ margin: 0 }}>The server accepts a workspace API key (<code>sf_live_…</code>). An administrator creates one under <Link className="link" href="/admin#keys">Admin → API keys</Link>; it is shown once. Keep it in an environment variable, never in a shared file.</p>
      </section>

      <section className="card card-pad mb-6">
        <div className="h3" style={{ marginTop: 0 }}>3 · Add it to your tool</div>
        <div className="connect-snips">
          {snippets.map((s) => (
            <div key={s.client} className="connect-snip">
              <div className="flex items-center justify-between gap-2"><b>{s.client}</b><CopyButton text={s.text} /></div>
              <div className="caption">{s.where}</div>
              <pre className="run-raw">{s.text}</pre>
            </div>
          ))}
        </div>
      </section>

      <section className="card card-pad">
        <div className="h3" style={{ marginTop: 0 }}>Tools on this server</div>
        <p className="caption">Every server also has <code>find_skill</code> (describe a task, get the right tool) and <code>get_run</code>.</p>
        {(() => {
          const live = rows.filter((r) => r.status === "published"), rest = rows.filter((r) => r.status !== "published");
          const table = (list: typeof rows, empty: string) => (
            <div className="tablewrap"><table className="mini"><thead><tr><th>Skill</th><th>What you get</th><th>Status here</th></tr></thead>
              <tbody>{list.map((r) => (
                <tr key={r.id}><td><Link className="link" href={`/repo/${r.id}`}>{r.name}</Link></td><td className="ink-2">{r.card}</td>
                  <td>{r.status === "published" ? <span className="pill pill-sm pill-sage">live tool</span> : <span className="caption">{r.status === "not added" ? "not in workspace" : "draft, not a tool yet"}</span>}</td></tr>
              ))}{list.length === 0 && <tr><td colSpan={3} className="none">{empty}</td></tr>}</tbody></table></div>);
          return (<>
            {table(live, "No live tools yet. Publish a skill in the Publish pipeline to make it a tool here.")}
            {rest.length > 0 && (
              <details className="mt-3">
                <summary className="caption" style={{ cursor: "pointer" }}>{rest.length} more skill{rest.length === 1 ? "" : "s"} become tools once published — <Link className="link" href="/pipeline">open the Publish pipeline</Link></summary>
                {table(rest, "")}
              </details>)}
          </>);
        })()}
      </section>
    </>
  );
}
