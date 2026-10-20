import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { LocalTime } from "@/components/LocalTime";
import { lastSyncs } from "@/lib/db/entities";
import { githubConfig } from "@/lib/github/app";
import { vercelConfig, supabaseConfig } from "@/lib/integrations/fetch";
import { IntegrationSync } from "@/components/integrations/SyncButton";
import { PortSync } from "@/components/integrations/PortSync";
import { CopyButton } from "@/components/CopyButton";
import { portConfig } from "@/lib/integrations/port/client";
import { AI_SKILL_BLUEPRINT, runSkillAction, runSkillWorkflow } from "@/lib/integrations/port/map";
import { headers } from "next/headers";

export const metadata = { title: "Integrations · Skills Factory" };
export const dynamic = "force-dynamic";
export const maxDuration = 60;

/** Data sources that fill the catalog. Read-only access; tokens stay in the deployment's environment. */
export default async function IntegrationsPage() {
  const ctx = await requireWorkspace();
  const canSync = ctx.role === "admin" || ctx.role === "author";
  const admin = ctx.role === "admin";
  const hh = await headers();
  const origin = `${hh.get("x-forwarded-proto") ?? "https"}://${hh.get("x-forwarded-host") ?? hh.get("host")}`;
  const [syncs, counts, insts] = await Promise.all([
    lastSyncs(ctx.supabase, ctx.workspace.id),
    ctx.supabase.from("sf_catalog_entities").select("kind").eq("workspace_id", ctx.workspace.id).eq("archived", false),
    ctx.supabase.from("sf_github_installations").select("installation_id").eq("workspace_id", ctx.workspace.id),
  ]);
  const n = (k: string) => ((counts.data ?? []) as { kind: string }[]).filter((e) => e.kind === k).length;
  const gh = githubConfig(), vc = vercelConfig(), sbc = supabaseConfig();
  const cards = [
    { id: "github", name: "GitHub", what: "Repositories: stack, owners, skills that apply, AI assets, scorecards, delivery metrics, PR gates.", ok: gh.ok && (insts.data ?? []).length > 0,
      setup: gh.ok ? "Connected through the GitHub App." : "Set up the GitHub App from the Catalog.", count: `${n("repository")} repositories`, manage: <Link className="btn btn-secondary btn-sm" href="/catalog">Open Catalog</Link> },
    { id: "vercel", name: "Vercel", what: "Services (projects): framework, production URL, production deployments (true deploy frequency), the repository each is built from and the Supabase project it uses.", ok: vc.ok,
      setup: vc.ok ? "Read token set on the server." : "Create a read token at vercel.com/account/settings/tokens and set VERCEL_TOKEN (and VERCEL_TEAM_ID for a team) in the deployment.", count: `${n("service")} services`,
      manage: canSync ? <IntegrationSync provider="vercel" disabled={!vc.ok} /> : null },
    { id: "supabase", name: "Supabase", what: "Databases (projects): region, status, Postgres version, and which services use each.", ok: sbc.ok,
      setup: sbc.ok ? "Access token set on the server." : "Create an access token at supabase.com/dashboard/account/tokens and set SUPABASE_ACCESS_TOKEN in the deployment.", count: `${n("database")} databases`,
      manage: canSync ? <IntegrationSync provider="supabase" disabled={!sbc.ok} /> : null },
  ];
  return (
    <>
      <PageHead eyebrow="Catalog · integrations" title="Where the catalog" em="comes from" after="."
        lead="GitHub, Vercel and Supabase are read-only: each fills the catalog with what it finds, linked to everything else. Port is the one that writes: it publishes your governed skills into a Port.io portal." />
      <p className="caption mb-4"><Link className="link" href="/catalog">Catalog</Link> · Syncing Vercel also refreshes delivery metrics, so linked repositories count real production deployments.</p>
      <div className="stack">{cards.map((c) => { const s = syncs[c.id]; return (
        <section key={c.id} className="card card-pad">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div style={{ minWidth: 0, flex: "1 1 320px" }}>
              <div className="h3" style={{ margin: 0 }}>{c.name} <span className={`pill pill-sm ${c.ok ? "pill-sage" : "pill-hold"}`}>{c.ok ? "connected" : "not set up"}</span></div>
              <p style={{ margin: "6px 0" }}>{c.what}</p>
              <p className="caption" style={{ margin: 0 }}>{c.setup}</p>
              <p className="caption" style={{ margin: "4px 0 0" }}><b>{c.count}</b> in the catalog{s ? <> · last sync <LocalTime iso={s.started_at} /> — {s.status}{s.error ? `: ${s.error}` : ""}</> : " · never synced"}</p>
            </div>
            <div>{c.manage}</div>
          </div>
        </section>); })}</div>

      {(() => {
        const pc = portConfig(process.env);
        const keySet = !!process.env.PORT_SF_API_KEY?.trim();
        const ready = pc.ok && keySet;
        const missing = [...(pc.ok ? [] : pc.missing), ...(keySet ? [] : ["PORT_SF_API_KEY"])];
        const actionJson = JSON.stringify(runSkillAction(`${origin}/api/port/actions`), null, 2);
        const workflowJson = JSON.stringify(runSkillWorkflow(`${origin}/api/port/actions`), null, 2);
        return (
          <section className="card card-pad mt-6">
            <div className="h3" style={{ margin: 0 }}>Port <span className={`pill pill-sm ${ready ? "pill-sage" : "pill-hold"}`}>{ready ? "configured" : "not set up"}</span> <span className="caption">writes to Port</span></div>
            <p style={{ margin: "6px 0" }}>Publishes your governed skills into a Port.io portal: an <b>AI Skill</b> catalog type (version, eval pass rate, approval, library status, inputs), a <b>Run skill</b> action that runs them here under the same validation, limits and audit, and your MCP server as a Port connector.</p>
            <p className="caption" style={{ margin: 0 }}>{ready ? <>Port API: <code>{pc.ok ? pc.apiUrl : ""}</code>. Built to Port&apos;s published API; verify each step on the first live run (docs/PORT.md).</> : <>Set in Vercel (sensitive): {missing.map((m, i) => <span key={m}>{i ? ", " : ""}<code>{m}</code></span>)}{pc.ok ? "" : <> · optional <code>PORT_API_URL</code> (https://api.us.port.io for US accounts)</>}. Setup: docs/PORT.md.</>}</p>
            {admin && <div className="mt-3"><PortSync disabled={!pc.ok} /></div>}
            <details className="mt-3"><summary className="caption" style={{ cursor: "pointer" }}><b>Run governed skill workflow</b>: in Port, Workflows → + Workflow → workflow JSON, paste. Needs the Port secret <code>SF_API_KEY</code> (a workspace API key).</summary>
              <div className="flex justify-end mb-1"><CopyButton text={workflowJson} /></div><pre className="run-raw">{workflowJson}</pre></details>
            <details className="mt-2"><summary className="caption" style={{ cursor: "pointer" }}><b>Classic self-service action</b> (older Port orgs): Self-service → + Action → Edit JSON</summary>
              <div className="flex justify-end mb-1"><CopyButton text={actionJson} /></div><pre className="run-raw">{actionJson}</pre></details>
            <details className="mt-2"><summary className="caption" style={{ cursor: "pointer" }}><b>MCP connector</b>: Port → Settings → Data sources → + Connector → MCP Servers → Custom Server</summary>
              <ul className="caption"><li>URL: <code>{origin}/api/mcp</code> <CopyButton text={`${origin}/api/mcp`} /></li><li>Header: <code>Authorization: Bearer {"{{ .secrets[\"SF_API_KEY\"] }}"}</code> (store a workspace API key as the Port secret <code>SF_API_KEY</code>)</li><li>Allowed tools: pick the skills Port&apos;s agents may call.</li></ul></details>
            <details className="mt-2"><summary className="caption" style={{ cursor: "pointer" }}><b>AI Skill blueprint</b> (created automatically on the first push)</summary><pre className="run-raw">{JSON.stringify(AI_SKILL_BLUEPRINT, null, 2)}</pre></details>
          </section>);
      })()}
    </>
  );
}
