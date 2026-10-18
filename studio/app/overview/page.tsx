import Link from "next/link";
import { getContext, fmtDate, type RunRow, type ReleaseStateRow, type SkillRow, type VersionRow } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { createWorkspace, selectWorkspace } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { PageHead, SectionHead } from "@/components/PageHead";
import { RunPill, VersionPill } from "@/components/factory/Pills";
import { EmptyState } from "@/components/factory/EmptyState";
import { skills as repoSkills, upstream } from "@/lib/data";

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

  const domains = Object.entries(repoSkills.reduce<Record<string, number>>((m, k) => ((m[k.domain] = (m[k.domain] ?? 0) + 1), m), {}));
  const imported = new Set(skills.map((k) => k.slug));
  const notImported = repoSkills.filter((k) => !imported.has(k.name)).length;
  const succeededPct = runs.length ? `${Math.round((count("succeeded") / runs.length) * 100)}%` : "—";

  const pipeline: { n: string; t: string; d: string }[] = [
    { n: "1", t: "Library", d: `${repoSkills.length + upstream.length} skills` },
    { n: "2", t: "Prove", d: "test + evaluate on real inputs" },
    { n: "3", t: "Approve", d: "reviewer signs the exact version" },
    { n: "4", t: "Use", d: "frozen version, called by API" },
  ];

  return (
    <>
      <PageHead eyebrow={`Overview · ${ws.name}`} title="AI skills you can" em="trust" after="."
        lead={`A library of ${repoSkills.length + upstream.length} AI skills — ${repoSkills.length} of ours that run, ${upstream.length} vetted from GitHub. Each is tested on real inputs and approved before people or apps can use it.`}
        caption={ctx.memberships.length > 1 ? <WorkspaceSwitcher ctx={ctx} /> : <>You are <b>{ctx.role}</b> in {ws.name}.</>} />

      <ol className="pipeline" aria-label="How a skill gets to use">
        {pipeline.map((p) => <li key={p.n}><span className="pipeline-n">{p.n}</span><span><b>{p.t}</b><span className="caption"> · {p.d}</span></span></li>)}
      </ol>

      <div className="summary-grid section-tight">
        <Link href="/repo" className="card summary row-link" title="Skills authored in this repository, each with scripts, declared inputs, output checks and evaluation cases">
          <div className="summary-value">{repoSkills.length}</div>
          <div className="summary-label">our runnable skills<div className="caption">{domains.map(([d, n]) => `${d} ${n}`).join(" · ")}</div></div>
        </Link>
        <Link href="/upstream" className="card summary row-link" title="Top public Agent Skills vendored verbatim, pinned by commit, license tracked">
          <div className="summary-value">{upstream.length}</div>
          <div className="summary-label">vetted from GitHub<div className="caption">pinned · licensed · reference</div></div>
        </Link>
        <Link href="/" className="card summary row-link" title="Skills imported or authored in this workspace; only these go through test, review and publish">
          <div className="summary-value">{skills.length}<span className="muted" style={{ fontSize: 20 }}>/{repoSkills.length}</span></div>
          <div className="summary-label">in this workspace<div className="caption">{notImported ? `${notImported} not imported yet` : "all imported"}</div></div>
        </Link>
        <div className="card summary" title="Skills with a published, immutable version callable through the API">
          <div className="summary-value">{published}</div>
          <div className="summary-label">published<div className="caption">callable by API</div></div>
        </div>
        <div className="card summary" title="Test and API runs (evaluation cases excluded — they are scored by pass rate) in the last 7 days">
          <div className="summary-value">{succeededPct}</div>
          <div className="summary-label">runs succeeded<div className="caption">{runs.length} test/API runs · 7 days{runs.some((r) => r.cost_usd != null) ? ` · ≈$${spend.toFixed(4)}` : ""}</div></div>
        </div>
      </div>

      {notImported > 0 && can(ctx.role, "skill.create") && (
        <p className="caption mt-3"><Link href="/?import=1" className="link-flame">Import the other {notImported} skills →</Link> to test, approve and publish them here.</p>
      )}

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
