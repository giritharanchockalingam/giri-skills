import Link from "next/link";
import { headers } from "next/headers";
import { requireWorkspace } from "@/lib/factory/db";
import { loadCatalog, type CatalogEntityRow } from "@/lib/db/catalog";
import { PageHead } from "@/components/PageHead";
import { levelOf, factsOf, LEVEL_LABEL, type LevelOrNone } from "@/lib/scorecards/levels";
import { LevelBadge } from "@/components/catalog/LevelBadge";
import { githubConfig } from "@/lib/github/app";
import { appManifest } from "@/lib/github/manifest";
import { CreateGithubApp } from "@/components/catalog/CreateGithubApp";
import { SyncButton } from "@/components/catalog/SyncButton";
import { ScoreAll } from "@/components/catalog/ScoreAll";
import { CHECKS } from "@/lib/scorecards/checks";
import { connectGithub, disconnectGithub } from "./actions";
import { humanName } from "@/lib/names";

export const metadata = { title: "Catalog · Skills Factory" };
export const dynamic = "force-dynamic";
export const maxDuration = 60;
const VERDICT_CLASS: Record<string, string> = { pass: "pill-sage", warn: "pill-hold", fail: "pill-rust", error: "pill-rust", skipped: "" };

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
type Entity = CatalogEntityRow;

/** Context Lake v1: what this workspace runs (from GitHub), what each repository is, and which skills apply to it. */
export default async function CatalogPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const ctx = await requireWorkspace();
  const admin = ctx.role === "admin";
  const cfg = githubConfig();
  const h = await headers();
  const origin = `${h.get("x-forwarded-proto") ?? "https"}://${h.get("x-forwarded-host") ?? h.get("host")}`;
  const catalog = await loadCatalog(ctx.supabase, ctx.workspace.id);
  const scores = new Map<string, { check_id: string; verdict: string; summary: string; created_at: string }[]>();
  for (const r of catalog.scores) scores.set(r.entity_id, [...(scores.get(r.entity_id) ?? []), r]);
  const canScore = ctx.role === "admin" || ctx.role === "author";
  const titleOf = (id: string) => CHECKS.find((c) => c.id === id)?.title ?? id;
  const insts = catalog.installations;
  const all: Entity[] = catalog.entities;
  const active = all.filter((e) => !e.archived);
  const stackFilter = sp.stack ?? null;
  const rows = stackFilter ? active.filter((e) => e.properties.stack?.some((s) => s.id === stackFilter)) : active;
  const last = catalog.lastSync;
  const stackCounts = new Map<string, { label: string; n: number }>();
  for (const e of active) for (const s of e.properties.stack ?? []) stackCounts.set(s.id, { label: s.label, n: (stackCounts.get(s.id)?.n ?? 0) + 1 });
  const noTests = active.filter((e) => (e.properties.counts?.files ?? 0) > 5 && !(e.properties.counts?.tests)).length;
  const noCi = active.filter((e) => (e.properties.counts?.files ?? 0) > 5 && !(e.properties.counts?.workflows)).length;
  const withMig = active.filter((e) => (e.properties.counts?.migrations ?? 0) > 0).length;
  const scoredRepos = active.filter((e) => scores.has(e.id));
  const passingRepos = scoredRepos.filter((e) => (scores.get(e.id) ?? []).every((r) => r.verdict === "pass" || r.verdict === "skipped")).length;
  const levels = new Map(active.map((e) => [e.id, levelOf(factsOf(e.properties), scores.get(e.id) ?? [])]));
  const levelCount = (l: LevelOrNone) => active.filter((e) => levels.get(e.id)?.level === l).length;

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
          <div className="cat-tile"><b>{scoredRepos.length ? `${passingRepos}/${scoredRepos.length}` : "—"}</b><span>{scoredRepos.length ? "scored repositories passing every check" : "not scored yet"}</span></div>
        </div>
        <div className="card card-pad mb-4 level-strip">
          <div className="flex flex-wrap items-center gap-3">
            {(["gold", "silver", "bronze", "none", "n/a"] as LevelOrNone[]).map((l) => <span key={l} className="level-count"><LevelBadge level={l} /> <b>{levelCount(l)}</b></span>)}
          </div>
          <div className="caption">Levels: Bronze — every check that applies has run · Silver — none fails · Gold — all pass. <Link className="link" href="/initiatives">Initiatives</Link> set a level as a goal with an owner and a deadline. <Link className="link" href="/ai-assets">AI assets</Link> lists the agents, MCP servers and skills in these repositories.</div>
        </div>
        {canScore && <div className="mb-4 flex flex-wrap items-center gap-3"><ScoreAll entities={active.map((e) => ({ id: e.id, key: e.key }))} label={scoredRepos.length ? "Re-run scorecards" : "Run scorecards"} />
          <span className="caption">Runs {CHECKS.length} checks where they apply ({CHECKS.map((c) => c.title.split(" (")[0]).join(", ")}) on each repository&apos;s current default branch. Read-only.</span></div>}
        <div className="flex flex-wrap gap-2 mb-4" aria-label="Filter by stack">
          <Link href="/catalog" className={`chip${!stackFilter ? " chip-on" : ""}`}>All · {active.length}</Link>
          {[...stackCounts.entries()].sort((a, b) => b[1].n - a[1].n).map(([id, s]) => (
            <Link key={id} href={`/catalog?stack=${id}`} className={`chip${stackFilter === id ? " chip-on" : ""}`}>{s.label} · {s.n}</Link>
          ))}
        </div>
        <div className="card">
          <div className="tablewrap"><table className="mini cat-table">
            <thead><tr><th>Repository</th><th>Built with</th><th>Level</th><th>Scorecard</th><th>Owner</th><th>Last change</th><th>Skills that apply</th></tr></thead>
            <tbody>{rows.map((e) => {
              const ap = e.properties.applicable ?? [];
              return (
                <tr key={e.id}>
                  <td><a className="link" href={e.url} target="_blank" rel="noreferrer"><b>{e.key}</b></a>{e.properties.visibility === "private" && <span className="caption"> · private</span>}
                    {e.properties.description && <div className="caption">{e.properties.description}</div>}</td>
                  <td>{(e.properties.stack ?? []).filter((s) => s.id !== "tests").map((s) => <span key={s.id} className="chip chip-sm" title={s.evidence.join("\n")}>{s.label}</span>)}
                    {e.properties.tree_truncated && <div className="caption">very large repository: partial file list</div>}</td>
                  <td><Link href={`/catalog/${e.id}`} title={levels.get(e.id)?.blockers.map((b) => `${b.title}: ${b.reason}`).join("\n") || LEVEL_LABEL[levels.get(e.id)?.level ?? "n/a"]}><LevelBadge level={levels.get(e.id)?.level ?? "n/a"} /></Link></td>
                  <td>{(scores.get(e.id) ?? []).length === 0 ? <span className="caption">not scored</span> : (
                    <Link href={`/catalog/${e.id}`} className="cat-score">{(scores.get(e.id) ?? []).sort((a, b) => a.check_id.localeCompare(b.check_id)).map((r) => (
                      <span key={r.check_id} className={`pill pill-sm ${VERDICT_CLASS[r.verdict] ?? ""}`} title={`${titleOf(r.check_id)}: ${r.summary}`}>{titleOf(r.check_id).split(" (")[0]}: {r.verdict}</span>
                    ))}</Link>)}</td>
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
          </table></div>
        </div>

      </>)}
      {cfg.ok && insts.length > 0 && active.length === 0 && <p className="none">No repositories yet. Choose <b>Sync now</b>, or add repositories to the installation on GitHub.</p>}
    </>
  );
}
