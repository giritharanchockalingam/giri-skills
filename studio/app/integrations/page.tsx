import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { LocalTime } from "@/components/LocalTime";
import { lastSyncs } from "@/lib/db/entities";
import { githubConfig } from "@/lib/github/app";
import { vercelConfig, supabaseConfig } from "@/lib/integrations/fetch";
import { IntegrationSync } from "@/components/integrations/SyncButton";

export const metadata = { title: "Integrations · Skills Factory" };
export const dynamic = "force-dynamic";
export const maxDuration = 60;

/** Data sources that fill the catalog. Read-only access; tokens stay in the deployment's environment. */
export default async function IntegrationsPage() {
  const ctx = await requireWorkspace();
  const canSync = ctx.role === "admin" || ctx.role === "author";
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
        lead="Each integration reads one system with read-only access and fills the catalog with what it finds, linked to everything else. Nothing is written back." />
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
    </>
  );
}
