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
import { listEntities, allRelations, type EntityRow } from "@/lib/db/entities";
import { ServicesTable, DatabasesTable, ComponentsTable } from "@/components/catalog/EntityViews";

export const metadata = { title: "Catalog · Skills Factory" };
export const dynamic = "force-dynamic";
export const maxDuration = 60;

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
  const [catalog, services, databases, components] = await Promise.all([loadCatalog(ctx.supabase, ctx.workspace.id), listEntities(ctx.supabase, ctx.workspace.id, "service"), listEntities(ctx.supabase, ctx.workspace.id, "database"), listEntities(ctx.supabase, ctx.workspace.id, "component")]);
  const kindCounts = { repository: catalog.entities.filter((e) => !e.archived).length, service: services.length, database: databases.length, component: components.length };
  if (sp.type === "component") {
    const rels = await allRelations(ctx.supabase, ctx.workspace.id);
    const all = new Map<string, EntityRow>([...services, ...databases, ...components, ...(catalog.entities as unknown as EntityRow[])].map((e) => [e.id, e]));
    return (
      <>
        <PageHead eyebrow="Platform · Delivery data" title="How it" em="ships" after="." lead="Everything the connected delivery tools know: pull requests, CI workflows and runs, deployments, environments and teams, each linked to the repositories and services above." />
        {components.length ? <ComponentsTable rows={components} all={all} rels={rels} type={sp.of ?? null} />
          : <section className="card card-pad"><p className="none" style={{ margin: 0 }}>Nothing yet. An administrator syncs the delivery catalog on <Link className="link" href="/integrations">Integrations</Link>.</p></section>}
      </>
    );
  }
  if (sp.type === "service" || sp.type === "database") {
    const rels = await allRelations(ctx.supabase, ctx.workspace.id);
    const all = new Map<string, EntityRow>([...services, ...databases, ...(catalog.entities as unknown as EntityRow[])].map((e) => [e.id, e]));
    const rows = sp.type === "service" ? services : databases;
    return (
      <>
        <PageHead eyebrow={sp.type === "service" ? "Platform · Services" : "Platform · Databases"} title="What you" em="run" after="." lead={sp.type === "service" ? "Services from Vercel: what each is built from, where it runs in production, how often it ships, and the database it uses." : "Databases from Supabase, and the services that use each."} />
        {rows.length ? (sp.type === "service" ? <ServicesTable rows={rows} all={all} rels={rels} /> : <DatabasesTable rows={rows} all={all} rels={rels} />)
          : <section className="card card-pad"><p className="none" style={{ margin: 0 }}>None yet — connect and sync {sp.type === "service" ? "Vercel" : "Supabase"} on <Link className="link" href="/integrations">Integrations</Link>.</p></section>}
      </>
    );
  }
  const scores = new Map<string, { check_id: string; verdict: string; summary: string; created_at: string }[]>();
  for (const r of catalog.scores) scores.set(r.entity_id, [...(scores.get(r.entity_id) ?? []), r]);
  const canScore = ctx.role === "admin" || ctx.role === "author";
  const insts = catalog.installations;
  const all: Entity[] = catalog.entities;
  const active = all.filter((e) => !e.archived);
  const stackFilter = sp.stack ?? null;
  const applies = (e: Entity) => (e.properties.applicable ?? []).length > 0;
  const withSkills = active.filter(applies).length;
  const noOwner = active.filter((e) => !e.owner).length;
  const rows = (sp.apply ? active.filter(applies) : stackFilter ? active.filter((e) => e.properties.stack?.some((s) => s.id === stackFilter)) : active)
    .slice().sort((a, b) => Number(applies(b)) - Number(applies(a)) || (b.last_activity_at ?? "").localeCompare(a.last_activity_at ?? ""));
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
      <PageHead eyebrow="Platform · Repositories" title="Where skills" em="apply" after="."
        lead="Your GitHub repositories, read-only. For each one: which skills apply to it, with the files that prove it, and whether it passes the engineering checks you enforce." />

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
                  {admin && <form action={disconnectGithub}><input type="hidden" name="installation_id" value={i.installation_id} /><button className="link caption" type="submit">Disconnect</button></form>}
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
          <Link href="/catalog?apply=1" className="cat-tile"><b>{withSkills} of {active.length}</b><span>repositories have skills that apply — run them from each row</span></Link>
          <a href="#checks" className="cat-tile"><b>{scoredRepos.length ? `${passingRepos} of ${scoredRepos.length}` : "—"}</b><span>{scoredRepos.length ? "checked repositories pass every check" : "not checked yet — run the checks below"}</span></a>
          <div className="cat-tile"><b>{noOwner}</b><span>without an owner (no CODEOWNERS file)</span></div>
        </div>
        <p className="caption mb-4">Gaps found in the files: {noCi} without CI, {noTests} without tests, {withMig} with database migrations (the database skills apply to these).</p>
        <div className="card card-pad mb-4 level-strip" id="checks">
          <div className="h3" style={{ marginTop: 0 }}>Engineering checks</div>
          <div className="flex flex-wrap items-center gap-3">
            {(["gold", "silver", "bronze", "none", "n/a"] as LevelOrNone[]).map((l) => <span key={l} className="level-count"><LevelBadge level={l} /> <b>{levelCount(l)}</b></span>)}
          </div>
          <div className="caption">Levels: Bronze — every check that applies has run · Silver — none fails · Gold — all pass. <Link className="link" href="/initiatives">Initiatives</Link> set a level as a goal with an owner and a deadline. <Link className="link" href="/ai-assets">AI assets</Link> lists the agents, MCP servers and skills found in these repositories.</div>
        </div>
        {canScore && <div className="mb-4 flex flex-wrap items-center gap-3"><ScoreAll entities={active.map((e) => ({ id: e.id, key: e.key }))} label={scoredRepos.length ? "Re-run scorecards" : "Run scorecards"} />
          <span className="caption">Runs {CHECKS.length} checks where they apply ({CHECKS.map((c) => c.title.split(" (")[0]).join(", ")}) on each repository&apos;s current default branch. Read-only.</span></div>}
        <div className="flex flex-wrap gap-2 mb-4" aria-label="Filter by stack">
          <Link href="/catalog" className={`chip${!stackFilter && !sp.apply ? " chip-on" : ""}`}>All · {active.length}</Link>
          <Link href="/catalog?apply=1" className={`chip${sp.apply ? " chip-on" : ""}`}>Skills apply · {withSkills}</Link>
          {[...stackCounts.entries()].sort((a, b) => b[1].n - a[1].n).map(([id, s]) => (
            <Link key={id} href={`/catalog?stack=${id}`} className={`chip${stackFilter === id ? " chip-on" : ""}`}>{s.label} · {s.n}</Link>
          ))}
        </div>
        <div className="card">
          <div className="tablewrap" id="repos"><table className="mini cat-table">
            <thead><tr><th>Repository</th><th>Skills that apply</th><th>Checks</th><th>Owner</th><th>Last change</th></tr></thead>
            <tbody>{rows.map((e) => {
              const ap = e.properties.applicable ?? [];
              return (
                <tr key={e.id}>
                  <td><a className="link" href={e.url} target="_blank" rel="noreferrer"><b>{e.key}</b></a>{e.properties.visibility === "private" && <span className="caption"> · private</span>}
                    {e.properties.description && <div className="caption">{e.properties.description}</div>}
                    <div className="mt-1">{(e.properties.stack ?? []).filter((s) => s.id !== "tests").map((s) => <span key={s.id} className="chip chip-sm" title={s.evidence.join("\n")}>{s.label}</span>)}
                    {e.properties.tree_truncated && <div className="caption">very large repository: partial file list</div>}</div></td>
                  <td>{ap.length === 0 ? <span className="caption" title="No library skill matches the files in this repository">none found</span> : (
                    <details><summary className="caption">{ap.length} skill{ap.length === 1 ? "" : "s"}: {ap.slice(0, 2).map((a) => humanName(a.skill.split("/")[1])).join(", ")}{ap.length > 2 ? "…" : ""}</summary>
                      <ul className="cat-why">{ap.map((a) => (
                        <li key={a.skill}><Link className="link" href={`/repo/${a.skill}/test?mode=existing`}>{humanName(a.skill.split("/")[1])}</Link> — {a.why}
                          <div className="caption">evidence: {a.evidence.map((x) => <code key={x} style={{ marginRight: 6 }}>{x}</code>)}</div></li>
                      ))}</ul></details>)}</td>
                  <td><Link href={`/catalog/${e.id}`} title={levels.get(e.id)?.blockers.map((b) => `${b.title}: ${b.reason}`).join("\n") || LEVEL_LABEL[levels.get(e.id)?.level ?? "n/a"]}><LevelBadge level={levels.get(e.id)?.level ?? "n/a"} /></Link></td>
                  <td>{e.owner ? <code>{e.owner}</code> : <span className="caption" title="No CODEOWNERS file assigns an owner. Add one (e.g. .github/CODEOWNERS with “* @team”) and sync.">Unassigned</span>}</td>
                  <td className="caption">{ago(e.last_activity_at)}</td>
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
