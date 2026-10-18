import Link from "next/link";
import { getContext, fmtDate, type RunRow, type ReleaseStateRow, type SkillRow, type VersionRow } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { createWorkspace, selectWorkspace } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { PageHead, SectionHead } from "@/components/PageHead";
import { RunPill, VersionPill } from "@/components/factory/Pills";
import { EmptyState } from "@/components/factory/EmptyState";

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
    sb.from("sf_runs").select("status, source, cost_usd").eq("workspace_id", ws.id).gte("created_at", since),
    sb.from("sf_runs").select("id, status, error, created_at, source, version_id, sf_skill_versions(version, sf_skills!sf_skill_versions_skill_id_fkey(slug, name))").eq("workspace_id", ws.id).in("status", ["failed", "timeout"]).gte("created_at", since).order("created_at", { ascending: false }).limit(8),
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

  const summary: { value: React.ReactNode; label: string; title: string }[] = [
    { value: skills.length, label: "skills in this workspace", title: "Count of sf_skills rows in the workspace, any status" },
    { value: published, label: "published skills", title: "Skills whose status is published (one published version each)" },
    { value: runs.length, label: "runs in the last 7 days", title: "Runs of any source (UI, API, evaluation) created in the last 7 days" },
    { value: runs.length ? `${Math.round((count("succeeded") / runs.length) * 100)}%` : "—", label: "succeeded (last 7 days)", title: "Runs with status succeeded ÷ all runs in the period; the output contract must have passed" },
    { value: runs.some((r) => r.cost_usd != null) ? `≈$${spend.toFixed(4)}` : "—", label: "estimated model spend (7 days)", title: "Sum of per-run cost estimates (provider-reported tokens × price table). Not a billing figure; — when no run used a model" },
  ];

  return (
    <>
      <PageHead eyebrow={`Overview · ${ws.name}`} title="What needs" em="attention" after="."
        lead={inReview.length || awaiting.length || failed.length
          ? `${inReview.length} version${inReview.length === 1 ? "" : "s"} waiting for review, ${awaiting.length} approved and ready to publish, ${failed.length} failed run${failed.length === 1 ? "" : "s"} in the last 7 days.`
          : skills.length ? "Nothing is waiting on you. Every number below is measured from this workspace's own records." : "This workspace has no skills yet. Create one or import the repository's skills to start."}
        caption={ctx.memberships.length > 1 ? <WorkspaceSwitcher ctx={ctx} /> : <>You are <b>{ctx.role}</b> in {ws.name}.</>} />

      <div className="summary-grid">
        {summary.map((c) => (
          <div key={c.label} className="card summary" title={c.title}>
            <div className="summary-value">{c.value}</div>
            <div className="summary-label">{c.label}</div>
          </div>
        ))}
      </div>
      <p className="caption mt-3">Period: last 7 days (runs); counts are live from the database. Hover a number for its definition. Model spend is an estimate flagged per run.</p>

      <div className="cards-3 section">
        <div className="card card-pad">
          <div className="h3">Pending reviews {can(ctx.role, "version.review") ? "for you" : ""} <span className="muted font-normal">({inReview.length})</span></div>
          <p className="caption">Versions in review. {can(ctx.role, "version.review") ? "You can approve or reject them." : "A reviewer or admin decides."}</p>
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
          <p className="caption">Approved versions whose evaluation gate and approval are both valid.</p>
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
          <div className="h3">Failed runs <span className="muted font-normal">({failed.length})</span></div>
          <p className="caption">Failed or timed-out runs in the last 7 days, newest first.</p>
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
