import { skillTitle } from "@/lib/names";
import Link from "next/link";
import { loadFunnel, loadPipeline } from "@/lib/db/skills";
import { publishedByLibrarySkill } from "@/lib/library";
import { loadActivity } from "@/lib/insights/load";
import { computeInsights } from "@/lib/insights/compute";
import { inboxCount } from "@/lib/db/actions";
import { ReadyQueue } from "@/components/factory/Funnel";
import { getContext, type WsCtx } from "@/lib/factory/db";
import { listRecentAgents } from "@/lib/db/agents";
import { createWorkspace, selectWorkspace } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { PageHead } from "@/components/PageHead";
import { TaskBox } from "@/components/factory/TaskBox";
import { lifecycle, stageSkills, roleOptions, modeHref, PHASES } from "@/lib/frontdoor";
import { LifecycleFilters } from "@/components/factory/LifecycleFilters";
import { ROLE_TEMPLATES } from "@/lib/factory/talentData";
import { Suspense } from "react";

export const metadata = { title: "Home · Skills Factory" };
export const dynamic = "force-dynamic";

/** The front door: start from the work (a task, a role, or a whole playbook) — not from the factory's internals. */
export default async function Home({ searchParams }: { searchParams: Promise<{ stage?: string; start?: string; role?: string }> }) {
  const sp = await searchParams;
  const c = await getContext();
  if (!c.workspace || !c.role) {
    return (
      <>
        <PageHead eyebrow="Welcome" title="Create your" em="workspace" after="." lead="A workspace holds your roles, playbooks, runs and the people who may use them. Whoever creates it becomes its administrator." />
        <div className="card card-pad" style={{ maxWidth: 560 }}>
          <ActionForm action={createWorkspace} submit="Create workspace">
            <div className="field"><label htmlFor="ws-name">Workspace name</label><input id="ws-name" name="name" className="input" required maxLength={120} placeholder="e.g. Finance Operations" /></div>
          </ActionForm>
          <p className="caption mt-4">Added to someone else&apos;s workspace? Their administrator adds you by your sign-in email ({c.user.email}).</p>
        </div>
      </>
    );
  }
  const ctx = c as WsCtx;
  const mode = sp.start === "existing" ? "existing" : "new";
  const role = ROLE_TEMPLATES.some((r) => r.name === sp.role) ? sp.role! : null;
  const phases = lifecycle(mode, role);
  const allStages = phases.flatMap((p) => p.stages);
  const stage = allStages.find((s) => s.id === sp.stage) ?? allStages.find((s) => s.count > 0) ?? allStages[0];   // a stage the starting point doesn't apply to stays selectable and says why
  const st = stageSkills(stage.id, mode, role);
  const rows = stage.why ? [] : st.rows;
  const otherMode = stage.why ? st.rows.length + st.otherMode : st.otherMode;
  const roleTitle = role ? ROLE_TEMPLATES.find((r) => r.name === role)?.title : null;
  const link = (patch: Record<string, string | null>) => {
    const n = new URLSearchParams(Object.entries({ stage: stage.id, start: mode, role }).filter(([, v]) => v) as [string, string][]);
    for (const [k, v] of Object.entries(patch)) { if (v) n.set(k, v); else n.delete(k); }
    return `/?${n.toString()}`;
  };
  const weekAgo = new Date(Date.now() - 7 * 86_400_000).toISOString();
  const [week, waiting] = await Promise.all([
    loadActivity(ctx.supabase, ctx.workspace.id, weekAgo).then(({ acts, baselines, scores }) => computeInsights(acts, baselines, scores, 7)),
    inboxCount(ctx.supabase, ctx.workspace.id),
  ]);
  const [recentAgents, { versions }, funnel] = await Promise.all([listRecentAgents(ctx.supabase, ctx.workspace.id), loadPipeline(ctx.supabase, ctx.workspace.id),
    ctx.role === "consumer" ? Promise.resolve([]) : loadFunnel(ctx.supabase, ctx.workspace.id)]);
  const suggestions = ["Check the RLS policies in my Supabase migration", "Is our AI chatbot high-risk under the EU AI Act?", "Estimate effort and price for this work breakdown"];
  const published = publishedByLibrarySkill(versions);

  return (
    <>
      <PageHead eyebrow={`Skills Factory · ${ctx.workspace.name}`} title="What do you need" em="done" after="?"
        lead="Describe the work and get a tested skill for it, or browse by stage of the AI lifecycle below."
        caption={ctx.memberships.length > 1 ? (
          <form action={selectWorkspace} className="flex flex-wrap items-center gap-2">
            <span>Workspace</span>
            <select name="workspace_id" className="select" style={{ width: "auto", minHeight: 36 }} defaultValue={ctx.workspace.id} aria-label="Workspace">
              {ctx.memberships.map((m) => <option key={m.workspace_id} value={m.workspace_id}>{m.workspace.name} ({m.role})</option>)}
            </select>
            <button type="submit" className="btn btn-secondary btn-sm">Switch</button>
          </form>) : undefined} />

      <TaskBox suggestions={suggestions} />
      <p className="caption home-proof">
        <Link href="/repo/" className="link"><b>{published.size}</b> skill{published.size === 1 ? "" : "s"} approved for use</Link> in {ctx.workspace.name}, usable here or from <Link href="/connect" className="link">Claude, Cursor or any app</Link>
        {week.total > 0 && <> · <Link href="/insights?days=7" className="link">{week.total} runs this week{week.successRate != null ? `, ${Math.round(week.successRate * 100)}% succeeded` : ""}</Link></>}
        {waiting > 0 && <> · <Link href="/inbox" className="link-flame">{waiting} decision{waiting === 1 ? "" : "s"} waiting on you →</Link></>}
      </p>
      {ctx.role !== "consumer" && <ReadyQueue items={funnel} />}

      <section className="section lc" aria-label="AI lifecycle">
        <Suspense fallback={null}><LifecycleFilters roles={roleOptions()} /></Suspense>

        <nav className="lc-rail" aria-label="Lifecycle stages">
          {phases.map((p) => (
            <div key={p.id} className={`lc-phase lc-phase-${p.id}`}>
              <div className="lc-phase-title">{p.title}</div>
              <div className="lc-stages">
                {p.stages.map((s) => (
                  <Link key={s.id} href={link({ stage: s.id })} scroll={false} aria-current={s.id === stage.id ? "page" : undefined}
                    className={`lc-stage${s.id === stage.id ? " on" : ""}${s.count === 0 ? " empty" : ""}`} aria-label={`${s.n ? `Stage ${s.n}: ` : ""}${s.name}, ${s.count} skill${s.count === 1 ? "" : "s"}`}>
                    <span className="lc-stage-name">{s.n ? <span className="lc-n">{s.n}</span> : null}{s.name}</span>
                    <span className="lc-count" title={`${s.count} skill${s.count === 1 ? "" : "s"}`}>{s.count}</span>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="lc-panel card">
          <div className="lc-panel-head">
            <div>
              <div className="eyebrow">{PHASES.find((p) => p.stages.includes(stage.id))?.title}</div>
              <h2 className="h2" style={{ margin: "2px 0 4px" }}>{stage.name}</h2>
              <p className="caption" style={{ margin: 0 }}>{stage.question}</p>
            </div>
            <div className="caption lc-panel-meta">
              {rows.length} skill{rows.length === 1 ? "" : "s"} · {mode === "new" ? "starting new" : "improving what exists"}{roleTitle ? ` · ${roleTitle}` : ""}
              {" · "}<Link className="link" href={role ? `/connect?kind=role&slug=${role}` : `/connect?kind=stage&slug=${stage.id}`}>Use in Claude, Cursor or VS Code</Link>
            </div>
          </div>
          {rows.length === 0 ? (
            <p className="lc-empty">{stage.why ?? <>No skill here for this starting point{roleTitle ? " and role" : ""} yet.</>}{" "}
              {otherMode > 0 && <Link className="link" href={link({ start: mode === "new" ? "existing" : "new" })} scroll={false}>See {otherMode} for {mode === "new" ? "improving what exists" : "starting new"}</Link>}</p>
          ) : (
            <><p className="caption lc-howto"><b>Try example</b> runs the skill on its own labelled sample inputs, so you see exactly what it produces. <b>Use mine</b> opens it ready for your own files and answers.</p>
            <ul className="lc-rows">
              {rows.map((r) => (
                <li key={r.id} className="lc-row">
                  <div className="lc-row-main">
                    <Link href={`/repo/${r.id}`} className="lc-row-name">{r.name}</Link>
                    {published.has(r.id) && <> <span className="pill pill-sage pill-sm" title={`Approved for use in ${ctx.workspace.name}: tested and signed off`}>Approved · v{published.get(r.id)}</span></>}
                    <div className="lc-row-out">{r.outcome}</div>
                    {r.bring && <div className="caption lc-row-bring">You bring: {r.bring}</div>}
                  </div>
                  <div className="lc-row-act">
                    {r.runnable && <Link href={modeHref(r.id, mode, true)} className="btn btn-primary btn-sm" title="Run it on its own sample inputs (fictional, labelled)">Try example</Link>}
                    <Link href={modeHref(r.id, mode, false)} className="btn btn-secondary btn-sm" title="Open it ready for your own files">Use mine</Link>
                  </div>
                </li>
              ))}
            </ul></>
          )}
          {rows.length > 0 && otherMode > 0 && (
            <p className="caption lc-foot">{otherMode} more in this stage only apply when {mode === "new" ? "improving what exists" : "starting new"}. <Link className="link" href={link({ start: mode === "new" ? "existing" : "new" })} scroll={false}>Show them</Link></p>
          )}
        </div>
      </section>

      {recentAgents.length > 0 && (
        <section className="section">
          <div className="h3 mb-2">Playbooks — several skills chained, with approvals</div>
          <ul className="lc-playbooks">
            {recentAgents.map((a) => (
              <li key={a.slug}><Link href={`/agents/${a.slug}/run`} className="lc-pb"><b>{skillTitle(a.name)}</b>{(() => { const d = (a.description || "").split(/[:.→]/)[0].trim(); const n = (x: string) => x.toLowerCase().replace(/[^a-z0-9]/g, ""); return d && n(d) !== n(a.name) ? <span className="caption">{d}</span> : null; })()}</Link></li>
            ))}
          </ul>
        </section>
      )}

      <p className="caption section">
        Every skill here can be tried on its own example; approved ones also run from your tools. Owners build and publish skills under <Link href="/pipeline" className="link">Build</Link>; approvals and audit are under <Link href="/inbox" className="link">Govern</Link>.
      </p>
    </>
  );
}
