import { LocalTime } from "@/components/LocalTime";
import Link from "next/link";
import { readableError } from "@/lib/runText";
import { humanName } from "@/lib/names";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { loadInbox, listActions } from "@/lib/db/actions";
import { Decide } from "@/components/inbox/Decide";
import { loadAccessRequests } from "@/lib/db/accessRequests";
import { ActionForm } from "@/components/factory/ActionForm";
import { decideAccess } from "@/app/accessActions";

export const metadata = { title: "Inbox · Skills Factory" };
export const dynamic = "force-dynamic";
export const maxDuration = 60;
const fmt = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { dateStyle: "medium", timeZone: "UTC" });
const CLS: Record<string, string> = { succeeded: "pill-sage", failed: "pill-rust", rejected: "pill-rust", pending_approval: "pill-hold" };

/** Human in the loop: everything waiting on a person, in one place. */
export default async function InboxPage() {
  const ctx = await requireWorkspace();
  const [d, recent, requests] = await Promise.all([loadInbox(ctx.supabase, ctx.workspace.id), listActions(ctx.supabase, ctx.workspace.id, { limit: 20 }), loadAccessRequests(ctx.supabase, ctx.workspace.id)]);
  const canDecide = ctx.role === "reviewer" || ctx.role === "admin";
  const isAdmin = ctx.role === "admin";
  const pendingAccess = requests.filter((r) => r.status === "pending" && isAdmin);
  const myRequests = requests.filter((r) => r.requested_by === ctx.user.id).slice(0, 10);
  const total = d.actions.length + d.agentRuns.length + d.reviews.length + d.overdue.length + pendingAccess.length;
  const decided = recent.filter((a) => a.status !== "pending_approval");

  return (
    <>
      <PageHead eyebrow="Human in the loop" title="Waiting on" em="you" after="."
        lead="Approvals, access requests and decisions that playbooks, actions and skills are waiting for: one place, newest first. Every decision is recorded in the audit log." />
      {total === 0 && <section className="card card-pad mb-6"><p className="none" style={{ margin: 0 }}>Nothing is waiting on a person.</p></section>}

      {pendingAccess.length > 0 && (
        <section className="section">
          <div className="h3">Access requests <span className="pill pill-sm pill-hold">{pendingAccess.length}</span></div>
          <div className="stack">{pendingAccess.map((r) => (
            <div key={r.id} className="card card-pad">
              <div><b>{r.requested_by_email ?? "A member"}</b> asks for the job role <b>{r.role_name}</b>{r.skill && <> to run <Link className="link" href={`/library/${r.skill}/`}>{humanName(r.skill.split("/").pop() ?? r.skill)}</Link></>}
                <div className="caption"><LocalTime iso={r.created_at} /></div></div>
              {r.note && <p style={{ margin: "6px 0" }}>“{r.note}”</p>}
              {r.requested_by === ctx.user.id ? <p className="caption">Your request — another admin decides.</p> : (
                <div className="mt-3 flex flex-wrap gap-2">
                  <ActionForm action={decideAccess} hidden={{ id: r.id, decision: "approve", note: "" }} submit="Approve and assign" submitClass="btn btn-primary btn-sm" />
                  <ActionForm action={decideAccess} hidden={{ id: r.id, decision: "decline", note: "" }} submit="Decline" submitClass="btn btn-secondary btn-sm" confirm={`Decline ${r.requested_by_email ?? "this"} request for ${r.role_name}?`} />
                </div>)}
            </div>))}</div>
        </section>)}

      {d.actions.length > 0 && (
        <section className="section">
          <div className="h3">Self-service actions to approve <span className="pill pill-sm pill-hold">{d.actions.length}</span></div>
          <div className="stack">{d.actions.map((a) => (
            <div key={a.id} className="card card-pad">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div><b>{a.skill}</b> on {a.entity_id ? <Link className="link" href={`/catalog/${a.entity_id}`}>{a.repo}</Link> : a.repo}
                  <div className="caption">asked by {a.requested_by_email ?? "a member"} · <LocalTime iso={a.created_at} />{a.uses_model ? " · uses a model" : ""}</div></div>
              </div>
              {a.reason && <p style={{ margin: "6px 0" }}>“{a.reason}”</p>}
              <div className="caption">Inputs: {Object.entries(a.inputs).map(([k, v]) => `${k} = ${"folder" in (v as object) ? (v as { folder: string }).folder : "text"}`).join(" · ") || "none"}</div>
              <div className="mt-3"><Decide id={a.id} mine={a.requested_by === ctx.user.id} canDecide={canDecide} /></div>
            </div>))}</div>
        </section>)}

      {d.agentRuns.length > 0 && (
        <section className="section">
          <div className="h3">Playbook runs at an approval gate <span className="pill pill-sm pill-hold">{d.agentRuns.length}</span></div>
          <ul className="ini-repos">{d.agentRuns.map((r) => <li key={r.id}><Link className="link" href={`/agent-runs/${r.id}`}>{r.agent}</Link> <span className="caption">started by {r.invoked_by_email ?? "a member"} · <LocalTime iso={r.started_at} /></span></li>)}</ul>
        </section>)}

      {d.reviews.length > 0 && (
        <section className="section">
          <div className="h3">Skill versions in review <span className="pill pill-sm pill-hold">{d.reviews.length}</span></div>
          <ul className="ini-repos">{d.reviews.map((v) => <li key={`${v.slug}-${v.version}`}><Link className="link" href={`/skills/${v.slug}/release`}>{v.name} v{v.version}</Link> <span className="caption">since <LocalTime iso={v.created_at} /></span></li>)}</ul>
        </section>)}

      {d.overdue.length > 0 && (
        <section className="section">
          <div className="h3">Initiatives past their deadline <span className="pill pill-sm pill-rust">{d.overdue.length}</span></div>
          <ul className="ini-repos">{d.overdue.map((i) => <li key={i.id}><Link className="link" href="/initiatives">{i.title}</Link> <span className="caption">owner {i.owner} · was due {fmt(i.due_on)}</span></li>)}</ul>
        </section>)}

      {myRequests.length > 0 && (
        <section className="section">
          <div className="h3">Your access requests</div>
          <ul className="ini-repos">{myRequests.map((r) => <li key={r.id}>{r.role_name}{r.skill ? ` (for ${humanName(r.skill.split("/").pop() ?? r.skill)})` : ""}: <span className={`pill pill-sm ${r.status === "approved" ? "pill-sage" : r.status === "declined" ? "pill-rust" : "pill-hold"}`}>{r.status}</span>
            <span className="caption"> · <LocalTime iso={r.decided_at ?? r.created_at} />{r.decided_by_email ? ` · by ${r.decided_by_email}` : ""}{r.decision_note ? ` · “${r.decision_note}”` : ""}</span></li>)}</ul>
        </section>)}

      {decided.length > 0 && (
        <section className="section">
          <div className="h3">Recent actions</div>
          <div className="card"><div className="tablewrap"><table className="mini cat-table"><thead><tr><th>When</th><th>Skill</th><th>Repository</th><th>Status</th><th>People</th><th>Result</th></tr></thead>
            <tbody>{decided.map((a) => <tr key={a.id}><td className="caption"><LocalTime iso={a.created_at} /></td><td>{humanName(a.skill)}</td><td>{a.entity_id ? <Link className="link" href={`/catalog/${a.entity_id}`}>{a.repo}</Link> : a.repo}</td>
              <td><span className={`pill pill-sm ${CLS[a.status] ?? ""}`}>{a.status.replace("_", " ")}</span></td>
              <td className="caption">{a.requested_by_email ?? "—"}{a.decided_by_email ? ` → ${a.decided_by_email}` : ""}{a.decision_note ? ` (“${a.decision_note}”)` : ""}</td>
              <td>{a.run_id ? <><Link className="link" href={`/runs/${a.run_id}`}>run</Link>{a.error && <div className={`caption${a.status === "failed" ? " ink-rust" : ""}`}>{readableError(a.error)}</div>}</> : a.error ? <span className="caption ink-rust">{readableError(a.error)}</span> : "—"}</td></tr>)}</tbody></table></div></div>
        </section>)}
    </>
  );
}
