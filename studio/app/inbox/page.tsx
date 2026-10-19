import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { loadInbox, listActions } from "@/lib/db/actions";
import { Decide } from "@/components/inbox/Decide";

export const metadata = { title: "Inbox · Skills Factory" };
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const when = (iso: string) => new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
const fmt = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { dateStyle: "medium", timeZone: "UTC" });
const CLS: Record<string, string> = { succeeded: "pill-sage", failed: "pill-rust", rejected: "pill-rust", pending_approval: "pill-hold" };

/** Human in the loop: everything waiting on a person, in one place. */
export default async function InboxPage() {
  const ctx = await requireWorkspace();
  const [d, recent] = await Promise.all([loadInbox(ctx.supabase, ctx.workspace.id), listActions(ctx.supabase, ctx.workspace.id, { limit: 20 })]);
  const canDecide = ctx.role === "reviewer" || ctx.role === "admin";
  const total = d.actions.length + d.agentRuns.length + d.reviews.length + d.overdue.length;
  const decided = recent.filter((a) => a.status !== "pending_approval");

  return (
    <>
      <PageHead eyebrow="Human in the loop" title="Waiting on" em="you" after="."
        lead="Approvals and decisions that agents, actions and skills are waiting for — one place, newest first. Every decision is recorded in the audit log." />
      {total === 0 && <section className="card card-pad mb-6"><p className="none" style={{ margin: 0 }}>Nothing is waiting on a person.</p></section>}

      {d.actions.length > 0 && (
        <section className="section">
          <div className="h3">Self-service actions to approve <span className="pill pill-sm pill-hold">{d.actions.length}</span></div>
          <div className="stack">{d.actions.map((a) => (
            <div key={a.id} className="card card-pad">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div><b>{a.skill}</b> on {a.entity_id ? <Link className="link" href={`/catalog/${a.entity_id}`}>{a.repo}</Link> : a.repo}
                  <div className="caption">asked by {a.requested_by_email ?? "a member"} · {when(a.created_at)}{a.uses_model ? " · uses a model" : ""}</div></div>
              </div>
              {a.reason && <p style={{ margin: "6px 0" }}>“{a.reason}”</p>}
              <div className="caption">Inputs: {Object.entries(a.inputs).map(([k, v]) => `${k} = ${"folder" in (v as object) ? (v as { folder: string }).folder : "text"}`).join(" · ") || "none"}</div>
              <div className="mt-3"><Decide id={a.id} mine={a.requested_by === ctx.user.id} canDecide={canDecide} /></div>
            </div>))}</div>
        </section>)}

      {d.agentRuns.length > 0 && (
        <section className="section">
          <div className="h3">Playbook runs at an approval gate <span className="pill pill-sm pill-hold">{d.agentRuns.length}</span></div>
          <ul className="ini-repos">{d.agentRuns.map((r) => <li key={r.id}><Link className="link" href={`/agent-runs/${r.id}`}>{r.agent}</Link> <span className="caption">started by {r.invoked_by_email ?? "a member"} · {when(r.started_at)}</span></li>)}</ul>
        </section>)}

      {d.reviews.length > 0 && (
        <section className="section">
          <div className="h3">Skill versions in review <span className="pill pill-sm pill-hold">{d.reviews.length}</span></div>
          <ul className="ini-repos">{d.reviews.map((v) => <li key={`${v.slug}-${v.version}`}><Link className="link" href={`/skills/${v.slug}/release`}>{v.name} v{v.version}</Link> <span className="caption">since {when(v.created_at)}</span></li>)}</ul>
        </section>)}

      {d.overdue.length > 0 && (
        <section className="section">
          <div className="h3">Initiatives past their deadline <span className="pill pill-sm pill-rust">{d.overdue.length}</span></div>
          <ul className="ini-repos">{d.overdue.map((i) => <li key={i.id}><Link className="link" href="/initiatives">{i.title}</Link> <span className="caption">owner {i.owner} · was due {fmt(i.due_on)}</span></li>)}</ul>
        </section>)}

      {decided.length > 0 && (
        <section className="section">
          <div className="h3">Recent actions</div>
          <div className="card"><div className="tablewrap"><table className="mini cat-table"><thead><tr><th>When</th><th>Skill</th><th>Repository</th><th>Status</th><th>People</th><th>Result</th></tr></thead>
            <tbody>{decided.map((a) => <tr key={a.id}><td className="caption">{when(a.created_at)}</td><td>{a.skill}</td><td>{a.entity_id ? <Link className="link" href={`/catalog/${a.entity_id}`}>{a.repo}</Link> : a.repo}</td>
              <td><span className={`pill pill-sm ${CLS[a.status] ?? ""}`}>{a.status.replace("_", " ")}</span></td>
              <td className="caption">{a.requested_by_email ?? "—"}{a.decided_by_email ? ` → ${a.decided_by_email}` : ""}{a.decision_note ? ` (“${a.decision_note}”)` : ""}</td>
              <td>{a.run_id ? <><Link className="link" href={`/runs/${a.run_id}`}>run</Link>{a.error && <div className={`caption${a.status === "failed" ? " ink-rust" : ""}`}>{a.error}</div>}</> : a.error ? <span className="caption ink-rust">{a.error}</span> : "—"}</td></tr>)}</tbody></table></div></div>
        </section>)}
    </>
  );
}
