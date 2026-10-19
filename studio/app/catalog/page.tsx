import Link from "next/link";
import { headers } from "next/headers";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { githubConfig } from "@/lib/github/app";
import { appManifest } from "@/lib/github/manifest";
import { CreateGithubApp } from "@/components/catalog/CreateGithubApp";
import { SyncButton } from "@/components/catalog/SyncButton";
import { connectGithub, disconnectGithub } from "./actions";
import { humanName } from "@/lib/names";
import type { Applicable, Signal } from "@/lib/github/detect";

export const metadata = { title: "Catalog · Skills Factory" };
export const dynamic = "force-dynamic";

const ERRORS: Record<string, string> = {
  "not-configured": "The GitHub App is not set up for this deployment yet.",
  "admin-only": "Only workspace administrators can connect GitHub.",
  "bad-state": "The GitHub round trip could not be verified (expired or for another user). Start again.",
  "missing-installation": "GitHub did not say which installation was made. Start again.",
  "no-oauth-code": "GitHub did not ask you to authorise the App, so access could not be verified. In the App's settings enable “Request user authorization (OAuth) during installation”, then try again.",
  "not-your-installation": "Your GitHub account cannot access that installation, so it was not linked.",
  "linked-elsewhere": "That GitHub installation is already linked to another workspace.",
  "save-failed": "The installation could not be saved.",
};
const ago = (iso: string | null) => {
  if (!iso) return "—";
  const d = (Date.now() - new Date(iso).getTime()) / 86_400_000;
  return d < 1 ? "today" : d < 2 ? "yesterday" : d < 60 ? `${Math.floor(d)} days ago` : `${Math.floor(d / 30)} months ago`;
};
type Entity = { id: string; key: string; title: string; url: string; owner: string | null; archived: boolean; last_activity_at: string | null;
  properties: { description?: string | null; visibility?: string; stack?: Signal[]; applicable?: Applicable[]; counts?: { files: number; tests: number; migrations: number; workflows: number }; tree_truncated?: boolean } };

/** Context Lake v1: what this workspace runs (from GitHub), what each repository is, and which skills apply to it. */
export default async function CatalogPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const ctx = await requireWorkspace();
  const admin = ctx.role === "admin";
  const cfg = githubConfig();
  const h = await headers();
  const origin = `${h.get("x-forwarded-proto") ?? "https"}://${h.get("x-forwarded-host") ?? h.get("host")}`;
  const [instQ, entQ, syncQ] = await Promise.all([
    ctx.supabase.from("sf_github_installations").select("installation_id, account_login, account_type, repository_selection, suspended_at, created_at").eq("workspace_id", ctx.workspace.id),
    ctx.supabase.from("sf_catalog_entities").select("id, key, title, url, owner, archived, last_activity_at, properties").eq("workspace_id", ctx.workspace.id).eq("kind", "repository").order("last_activity_at", { ascending: false, nullsFirst: false }),
    ctx.supabase.from("sf_catalog_syncs").select("status, counts, error, started_at, finished_at").eq("workspace_id", ctx.workspace.id).order("started_at", { ascending: false }).limit(1),
  ]);
  const insts = instQ.data ?? [];
  const all = (entQ.data ?? []) as Entity[];
  const active = all.filter((e) => !e.archived);
  const stackFilter = sp.stack ?? null;
  const rows = stackFilter ? active.filter((e) => e.properties.stack?.some((s) => s.id === stackFilter)) : active;
  const last = syncQ.data?.[0] ?? null;
  const stackCounts = new Map<string, { label: string; n: number }>();
  for (const e of active) for (const s of e.properties.stack ?? []) stackCounts.set(s.id, { label: s.label, n: (stackCounts.get(s.id)?.n ?? 0) + 1 });
  const noTests = active.filter((e) => (e.properties.counts?.files ?? 0) > 5 && !(e.properties.counts?.tests)).length;
  const noCi = active.filter((e) => (e.properties.counts?.files ?? 0) > 5 && !(e.properties.counts?.workflows)).length;
  const withMig = active.filter((e) => (e.properties.counts?.migrations ?? 0) > 0).length;

  return (
    <>
      <PageHead eyebrow="Context Lake" title="What you" em="run" after="."
        lead="Your repositories, read from GitHub: what each one is built with, who owns it, and which skills apply — with the files that prove it." />

      {sp.connected && <p className="notice notice-ok mb-4" role="status">Connected <b>{sp.connected}</b> — {sp.synced ?? 0} repositories synced.</p>}
      {sp.error && <p className="notice notice-err mb-4" role="alert">{ERRORS[sp.error] ?? "GitHub returned an error."}{sp.detail ? ` (${sp.detail})` : ""}</p>}
      {sp.disconnected && <p className="notice notice-info mb-4" role="status">Disconnected. Its repositories were removed from the catalog; uninstall the App on GitHub to revoke access there too.</p>}

      {!cfg.ok ? (
        <section className="card card-pad mb-6">
          <div className="h3" style={{ marginTop: 0 }}>Set up the GitHub App (once per deployment)</div>
          <p>The catalog reads GitHub through a private GitHub App with <b>read-only</b> access to repository contents and metadata, on the repositories you choose. No personal tokens.</p>
          {admin ? (<>
            <ol className="caption" style={{ margin: "0 0 12px 18px" }}>
              <li>Create the App on GitHub (one click below — the permissions are filled in).</li>
              <li>GitHub returns here and shows six values once: add them to the Vercel project&apos;s environment variables and redeploy.</li>
              <li>Come back and choose <b>Connect GitHub</b> to pick repositories.</li>
            </ol>
            <CreateGithubApp manifest={JSON.stringify(appManifest(origin))} />
            <p className="caption mt-3">Missing now: {cfg.missing.map((m) => <code key={m} style={{ marginRight: 6 }}>{m}</code>)}</p>
          </>) : <p className="none">A workspace administrator sets this up.</p>}
        </section>
      ) : insts.length === 0 ? (
        <section className="card card-pad mb-6">
          <div className="h3" style={{ marginTop: 0 }}>Connect GitHub</div>
          <p>Install the App on your account or organization and choose which repositories it may read. You will be asked to authorise it so we can verify the installation is yours.</p>
          {admin ? <form action={connectGithub}><button className="btn btn-primary" type="submit">Connect GitHub</button></form> : <p className="none">A workspace administrator connects GitHub.</p>}
        </section>
      ) : (
        <section className="card card-pad mb-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              {insts.map((i) => (
                <div key={i.installation_id} className="flex flex-wrap items-center gap-2">
                  <b>{i.account_login}</b><span className="caption">{i.account_type} · {i.repository_selection === "all" ? "all repositories" : "selected repositories"}{i.suspended_at ? " · suspended" : ""}</span>
                  {admin && <form action={disconnectGithub}><input type="hidden" name="installation_id" value={i.installation_id} /><button className="link caption" type="submit">disconnect</button></form>}
                </div>
              ))}
              <div className="caption">{last ? `Last sync ${ago(last.started_at)} · ${last.status}${last.status === "succeeded" ? ` · ${(last.counts as { repos?: number }).repos ?? 0} repositories` : last.error ? ` · ${last.error}` : ""}` : "Not synced yet"}</div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <SyncButton />
              {admin && <form action={connectGithub}><button className="btn btn-secondary btn-sm" type="submit">Add an account or repositories</button></form>}
            </div>
          </div>
        </section>
      )}

      {active.length > 0 && (<>
        <div className="cat-tiles mb-4">
          <div className="cat-tile"><b>{active.length}</b><span>repositories</span></div>
          <div className="cat-tile"><b>{withMig}</b><span>with database migrations</span></div>
          <div className="cat-tile"><b>{noCi}</b><span>without CI</span></div>
          <div className="cat-tile"><b>{noTests}</b><span>without tests</span></div>
        </div>
        <div className="flex flex-wrap gap-2 mb-4" aria-label="Filter by stack">
          <Link href="/catalog" className={`chip${!stackFilter ? " chip-on" : ""}`}>All · {active.length}</Link>
          {[...stackCounts.entries()].sort((a, b) => b[1].n - a[1].n).map(([id, s]) => (
            <Link key={id} href={`/catalog?stack=${id}`} className={`chip${stackFilter === id ? " chip-on" : ""}`}>{s.label} · {s.n}</Link>
          ))}
        </div>
        <div className="card">
          <table className="mini cat-table">
            <thead><tr><th>Repository</th><th>Built with</th><th>Owner</th><th>Last change</th><th>Skills that apply</th></tr></thead>
            <tbody>{rows.map((e) => {
              const ap = e.properties.applicable ?? [];
              return (
                <tr key={e.id}>
                  <td><a className="link" href={e.url} target="_blank" rel="noreferrer"><b>{e.key}</b></a>{e.properties.visibility === "private" && <span className="caption"> · private</span>}
                    {e.properties.description && <div className="caption">{e.properties.description}</div>}</td>
                  <td>{(e.properties.stack ?? []).filter((s) => s.id !== "tests").map((s) => <span key={s.id} className="chip chip-sm" title={s.evidence.join("\n")}>{s.label}</span>)}
                    {e.properties.tree_truncated && <div className="caption">very large repository: partial file list</div>}</td>
                  <td>{e.owner ? <code>{e.owner}</code> : <span className="caption">no CODEOWNERS</span>}</td>
                  <td className="caption">{ago(e.last_activity_at)}</td>
                  <td>{ap.length === 0 ? <span className="caption">—</span> : (
                    <details><summary className="caption">{ap.length} skill{ap.length === 1 ? "" : "s"}: {ap.slice(0, 2).map((a) => humanName(a.skill.split("/")[1])).join(", ")}{ap.length > 2 ? "…" : ""}</summary>
                      <ul className="cat-why">{ap.map((a) => (
                        <li key={a.skill}><Link className="link" href={`/repo/${a.skill}/test?mode=existing`}>{humanName(a.skill.split("/")[1])}</Link> — {a.why}
                          <div className="caption">evidence: {a.evidence.map((x) => <code key={x} style={{ marginRight: 6 }}>{x}</code>)}</div></li>
                      ))}</ul></details>)}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
        <p className="caption mt-3">Next: run the applicable skills on every repository automatically and score each one (scorecards).</p>
      </>)}
      {cfg.ok && insts.length > 0 && active.length === 0 && <p className="none">No repositories yet. Choose <b>Sync now</b>, or add repositories to the installation on GitHub.</p>}
    </>
  );
}
