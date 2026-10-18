import Link from "next/link";
import { getContext, fmtDate, type RunRow, type ReleaseStateRow, type SkillRow, type VersionRow } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { createWorkspace, selectWorkspace } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { PageHead, SectionHead } from "@/components/PageHead";
import { RunPill, VersionPill } from "@/components/factory/Pills";
import { EmptyState } from "@/components/factory/EmptyState";
import { skills as repoSkills, upstream, STAGES, SHELVES } from "@/lib/data";

export const metadata = { title: "Overview · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const ctx = await getContext();
  if (!ctx.workspace || !ctx.role) {
    return (
      <>
        <PageHead eyebrow="Overview" title="Create your" em="workspace" after="." lead="A workspace holds skills, versions, evaluations, runs and the people who may use them. The person who creates it becomes its administrator and can add members with roles." />
        <div className="card card-pad" style={{ maxWidth: 560 }}>
          <ActionForm action={createWorkspace} submit="Create workspace">
            <div className="field"><label htmlFor="ws-name">Workspace name</label><input id="ws-name" name="name" className="input" required maxLength={120} placeholder="e.g. Finance Operations" /></div>
          </ActionForm>
          <p className="caption mt-4">Not seeing a workspace you were added to? Memberships are added by that workspace&apos;s administrator using your sign-in email ({ctx.user.email}).</p>
        </div>
      </>
    );
  }
  const ws = ctx.workspace, sb = ctx.supabase;
  const since = new Date(Date.now() - 7 * 86400_000).toISOString();
  const [skillsQ, statesQ, runsQ, failedQ] = await Promise.all([
    sb.from("sf_skills").select("id, slug, name, status").eq("workspace_id", ws.id),
    sb.from("sf_version_release_state").select("*").eq("workspace_id", ws.id).in("status", ["in_review", "approved", "draft"]),
    sb.from("sf_runs").select("status, source, cost_usd").eq("workspace_id", ws.id).neq("source", "eval").gte("created_at", since),
    sb.from("sf_runs").select("id, status, error, created_at, source, version_id, sf_skill_versions(version, sf_skills!sf_skill_versions_skill_id_fkey(slug, name))").eq("workspace_id", ws.id).neq("source", "eval").in("status", ["failed", "timeout"]).gte("created_at", since).order("created_at", { ascending: false }).limit(8),
  ]);
  const skills = (skillsQ.data ?? []) as Pick<SkillRow, "id" | "slug" | "name" | "status">[];
  const bySkill = new Map(skills.map((s) => [s.id, s]));
  const states = (statesQ.data ?? []) as (ReleaseStateRow & { skill_id: string; version: number })[];
  const inReview = states.filter((s) => s.status === "in_review");
  const awaiting = states.filter((s) => s.status === "approved" && s.publishable);
  const runs = (runsQ.data ?? []) as Pick<RunRow, "status" | "source" | "cost_usd">[];
  const failed = (failedQ.data ?? []) as unknown as (Pick<RunRow, "id" | "status" | "error" | "created_at" | "source"> & { sf_skill_versions: Pick<VersionRow, "version"> & { sf_skills: { slug: string; name: string } } })[];
  const count = (st: string) => runs.filter((r) => r.status === st).length;
  const spend = runs.reduce((a, r) => a + (r.cost_usd == null ? 0 : Number(r.cost_usd)), 0);
  const published = skills.filter((s) => s.status === "published").length;

  const imported = new Set(skills.map((k) => k.slug));
  const publishedSlugs = new Set(skills.filter((k) => k.status === "published").map((k) => k.slug));
  const notImported = repoSkills.filter((k) => !imported.has(k.name)).length;
  const succeededPct = runs.length ? `${Math.round((count("succeeded") / runs.length) * 100)}%` : "—";
  const cover = (id: string) => {
    const lib = repoSkills.filter((k) => k.stage === id);
    return { lib: lib.length, ws: lib.filter((k) => imported.has(k.name)).length, pub: lib.filter((k) => publishedSlugs.has(k.name)).length };
  };
  const adlcCount = repoSkills.filter((k) => STAGES.some((st) => st.id === k.stage)).length;
  const gaps = STAGES.filter((st) => cover(st.id).lib === 0).length;

  return (
    <>
      <PageHead eyebrow={`Overview · ${ws.name}`} title="The AI lifecycle," em="runnable" after="."
        lead={`${adlcCount} skills across the ${STAGES.length} stages of building AI — each runs on real inputs, is evaluated, approved, and then callable by API. ${gaps ? `${gaps} stage${gaps === 1 ? "" : "s"} still uncovered.` : "Every stage covered."}`}
        caption={ctx.memberships.length > 1 ? <WorkspaceSwitcher ctx={ctx} /> : <>You are <b>{ctx.role}</b> in {ws.name}.</>} />

      <ol className="stage-grid" aria-label="AI development life cycle coverage">
        {STAGES.map((st) => { const c = cover(st.id); return (
          <li key={st.id}>
            <Link href={`/?stage=${st.id}`} className={`card stage-tile row-link${c.lib === 0 ? " stage-gap" : ""}`} title={st.question}>
              <span className="stage-n">{st.n}</span>
              <span className="stage-name">{st.name}</span>
              <span className="caption stage-q">{st.question}</span>
              <span className="stage-counts">{c.lib === 0 ? <span className="fail">gap</span> : <><b>{c.lib}</b> skill{c.lib === 1 ? "" : "s"} · {c.pub} published</>}</span>
            </Link>
          </li>); })}
      </ol>

      <div className="shelf-row">
        {SHELVES.map((sh) => { const c = cover(sh.id); return (
          <Link key={sh.id} href={`/?stage=${sh.id}`} className="card shelf-tile row-link"><b>{sh.name}</b><span className="caption"> · {c.lib} skills · {c.pub} published</span></Link>); })}
        <Link href="/upstream" className="card shelf-tile row-link"><b>GitHub reference</b><span className="caption"> · {upstream.length} vetted skills</span></Link>
      </div>

      <p className="caption mt-3">
        In this workspace: {skills.length} skills · {published} published · {succeededPct} of {runs.length} test/API runs succeeded (7 days){runs.some((r) => r.cost_usd != null) ? ` · ≈$${spend.toFixed(4)} model spend` : ""}.
        {notImported > 0 && can(ctx.role, "skill.create") && <> <Link href="/?import=1" className="link-flame">Import {notImported} more →</Link></>}
      </p>

      <SectionHead title="Needs" em="attention" caption={inReview.length || awaiting.length || failed.length ? `${inReview.length} to review · ${awaiting.length} to publish · ${failed.length} failed` : "Nothing is waiting on you."} />
      <div className="cards-3">
        <div className="card card-pad">
          <div className="h3">Pending reviews {can(ctx.role, "version.review") ? "for you" : ""} <span className="muted font-normal">({inReview.length})</span></div>
          
          <div className="list mt-3">
            {inReview.map((s) => { const sk = bySkill.get(s.skill_id); return sk && (
              <Link key={s.version_id} href={`/skills/${sk.slug}/release?v=${s.version}`} className="list-row row-link">
                <span className="name">{sk.name} <span className="muted">v{s.version}</span></span>
                <VersionPill status={s.status} small />
              </Link>); })}
            {inReview.length === 0 && <p className="none">No versions are waiting for review.</p>}
          </div>
        </div>
        <div className="card card-pad">
          <div className="h3">Ready to publish <span className="muted font-normal">({awaiting.length})</span></div>
          
          <div className="list mt-3">
            {awaiting.map((s) => { const sk = bySkill.get(s.skill_id); return sk && (
              <Link key={s.version_id} href={`/skills/${sk.slug}/release?v=${s.version}`} className="list-row row-link">
                <span className="name">{sk.name} <span className="muted">v{s.version}</span></span>
                <VersionPill status={s.status} small />
              </Link>); })}
            {awaiting.length === 0 && <p className="none">Nothing is approved and waiting.</p>}
          </div>
        </div>
        <div className="card card-pad">
          <div className="h3">Failed test/API runs <span className="muted font-normal">({failed.length})</span></div>
          
          <div className="list mt-3">
            {failed.map((r) => (
              <Link key={r.id} href={`/runs/${r.id}`} className="list-row row-link">
                <span className="min-w-0"><span className="name">{r.sf_skill_versions?.sf_skills?.name ?? "—"} <span className="muted">v{r.sf_skill_versions?.version}</span></span>
                  <div className="meta"><span>{fmtDate(r.created_at)}</span><span>{r.source}</span></div>
                  {r.error && <div className="caption" style={{ overflowWrap: "anywhere" }}>{r.error.slice(0, 140)}</div>}</span>
                <RunPill status={r.status} small />
              </Link>
            ))}
            {failed.length === 0 && <p className="none">No failed runs in the period.</p>}
          </div>
        </div>
      </div>

      {skills.length === 0 && (
        <section className="section">
          <SectionHead title="Start" em="here" caption="Two ways to get a first skill into the factory." />
          <div className="card"><EmptyState title="No skills yet" detail="Create a skill from scratch, or import any of the 40 repository skills (their scripts, instructions and evaluation cases come with them)." action="Go to Skills" href="/" /></div>
        </section>
      )}
    </>
  );
}

function WorkspaceSwitcher({ ctx }: { ctx: Awaited<ReturnType<typeof getContext>> }) {
  return (
    <form action={selectWorkspace} className="flex flex-wrap items-center gap-2">
      <span>You are <b>{ctx.role}</b> in</span>
      <select name="workspace_id" className="select" style={{ width: "auto", minHeight: 36 }} defaultValue={ctx.workspace?.id} aria-label="Workspace">
        {ctx.memberships.map((m) => <option key={m.workspace_id} value={m.workspace_id}>{m.workspace.name} ({m.role})</option>)}
      </select>
      <button type="submit" className="btn btn-secondary btn-sm">Switch</button>
    </form>
  );
}
