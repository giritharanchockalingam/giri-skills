import { skillTitle } from "@/lib/names";
import { LocalTime } from "@/components/LocalTime";
import Link from "next/link";
import { notFound } from "next/navigation";
import {requireWorkspace } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { PageHead } from "@/components/PageHead";
import { AgentRunDriver } from "@/components/factory/AgentRunDriver";
import { parseRef, isSkill } from "@/lib/factory/agents";
import { getAgentRun, getAgentVersionWithAgent } from "@/lib/db/agents";
import { mdToHtml } from "@/lib/markdown.mjs";

/** The "## Summary" section of a Markdown deliverable (the answer, before the detail). */
function summaryOf(md: string | null | undefined): string | null {
  if (!md) return null;
  const m = md.match(/^## Summary\s*\n([\s\S]*?)(?=\n## |$)/m);
  const body = (m ? m[1] : "").trim();
  return body ? body.split("\n").slice(0, 14).join("\n") : null;
}

export const dynamic = "force-dynamic";
export const metadata = { title: "Playbook run · Skills Factory" };

const TONE: Record<string, string> = { ok: "pill-sage", approved: "pill-sage", succeeded: "pill-sage", running: "pill-deep", awaiting_approval: "pill-hold", blocked: "pill-hold", failed: "pill-rust", needs_input: "pill-rust", skipped: "pill-none", cancelled: "pill-none" };
const LABEL: Record<string, string> = { ok: "ok", approved: "approved", succeeded: "done", running: "running", awaiting_approval: "awaiting approval", blocked: "blocked", failed: "failed", needs_input: "needs input", skipped: "skipped", cancelled: "cancelled" };

export default async function AgentRunPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ go?: string }> }) {
  const { id } = await params; const { go } = await searchParams;
  const ctx = await requireWorkspace();
  const run = await getAgentRun(ctx.supabase, ctx.workspace.id, id);
  if (!run) notFound();
  const version = await getAgentVersionWithAgent(ctx.supabase, run.agent_version_id);
  const spec = version.spec;
  const waiting = run.steps.find((s) => s.status === "awaiting_approval");
  // no deliverables chosen → the last step that wrote files is what the agent produced
  const lastWithFiles = [...run.steps].reverse().find((s) => s.files?.length);
  const outRefs = spec.outputs?.length ? spec.outputs : (lastWithFiles?.files ?? []).map((f) => `$steps.${lastWithFiles!.id}:${f.path}`);
  const deliverables = outRefs.map((ref) => { const p = parseRef(ref); if (p?.kind !== "step") return null; const rec = run.steps.find((s) => s.id === p.step); const f = rec?.files?.find((x) => x.path === p.file); return f ? { step: p.step, f } : null; }).filter(Boolean) as { step: string; f: { path: string; bytes: number; content_text: string | null } }[];

  return (
    <>
      <PageHead eyebrow={`Playbook run · v${version.version}`} title={skillTitle(version.sf_agents.name)} em=""
        lead={<><span className={`pill ${TONE[run.status]}`}>{LABEL[run.status]}</span> {run.error && <span className="caption"> {run.error}</span>}</>}
        caption={<>Started <LocalTime iso={run.created_at} /> · {run.steps.filter((s) => s.status === "ok" || s.status === "approved").length}/{spec.steps.length} steps{run.cost_usd != null ? ` · model cost ≈$${Number(run.cost_usd).toFixed(4)}` : ""} · <Link href={`/agents/${version.sf_agents.slug}?v=${version.version}`} className="link">configuration</Link></>} />
      {run.status !== "running" && (() => {
        const lead = deliverables.find((d) => d.f.path.endsWith(".md") && summaryOf(d.f.content_text));
        const blocked = run.steps.find((x) => x.status === "blocked" || x.status === "failed");
        const blockedMd = blocked?.files?.find((f) => f.path.endsWith(".md") && summaryOf(f.content_text));
        const show = blockedMd ? { step: blocked!.id, f: blockedMd } : lead;
        const headline = run.status === "succeeded" ? "Done — every step ran and passed its checks."
          : run.status === "awaiting_approval" ? `Waiting for a person: ${waiting?.role ?? "an approver"} must approve before it continues.`
          : run.status === "blocked" ? `Stopped by a gate at “${blocked?.id}” — this is a verdict, not a malfunction.`
          : run.status === "failed" ? `Failed at “${blocked?.id}”.` : null;
        return headline ? (
          <div className="card card-pad run-answer mb-5">
            <div className="h3" style={{ marginTop: 0 }}>{headline}</div>
            {show && <>
              <p className="caption">From <b>{show.step}</b> · {show.f.path}</p>
              <div className="prose run-prose" dangerouslySetInnerHTML={{ __html: mdToHtml(summaryOf(show.f.content_text) ?? "") }} />
            </>}
          </div>
        ) : null;
      })()}
      <AgentRunDriver runId={run.id} status={run.status} autoStart={go === "1"} canApprove={can(ctx.role, "agent.approve")} approvalRole={waiting?.role ?? null} />

      <ol className="ab-trace mt-5">
        {spec.steps.map((s, i) => {
          const rec = run.steps.find((x) => x.id === s.id);
          const status = rec?.status ?? (i === run.cursor && run.status === "running" ? "running" : "skipped");
          return (
            <li key={s.id} className="card ab-trace-step">
              <div className="ab-step-head">
                <span className="ab-n">{i + 1}</span><b>{s.id}</b>
                <span className={`pill pill-sm ${TONE[status] ?? "pill-none"}`}>{rec ? LABEL[status] : i < run.cursor ? "—" : "not reached"}</span>
                {isSkill(s) && <span className="caption">{s.skill}</span>}
                {rec?.checks_total ? <span className="caption">{rec.checks_passed}/{rec.checks_total} checks</span> : null}
                {rec?.cost_usd ? <span className="caption">≈${rec.cost_usd.toFixed(4)}</span> : null}
                {rec?.duration_ms ? <span className="caption">{(rec.duration_ms / 1000).toFixed(1)} s</span> : null}
              </div>
              {rec?.error && <p className="notice notice-err" style={{ margin: "8px 0 0" }}>{rec.error}</p>}
              {rec?.failed_checks && rec.failed_checks.length > 0 && (
                <ul className="ab-failed">{rec.failed_checks.map((c, k) => <li key={k}><code>{c.check}</code> on <b>{c.path}</b> — {c.evidence}</li>)}</ul>
              )}
              {rec?.status === "approved" && <p className="caption">Approved by {rec.approver_email || "reviewer"} as {rec.role}{rec.approval_note ? ` — “${rec.approval_note}”` : ""}</p>}
              {rec?.files && rec.files.length > 0 && (
                <div className="chip-group mt-2">{rec.files.map((f) => <a key={f.path} href={`#${s.id}-${f.path}`} className="chip">{f.path}</a>)}</div>
              )}
            </li>
          );
        })}
      </ol>

      {deliverables.length > 0 && (
        <section className="section stack">
          <div className="h3">Deliverables</div>
          {deliverables.map(({ step, f }) => (
            <details key={step + f.path} id={`${step}-${f.path}`} className="card card-pad" open={deliverables.length <= 2}>
              <summary><b>{f.path}</b> <span className="caption">from {step} · {f.bytes} bytes</span></summary>
              <pre className="ab-file">{f.content_text}</pre>
            </details>
          ))}
        </section>
      )}
      <section className="section stack">
        <div className="h3">All files</div>
        {run.steps.flatMap((s) => (s.files ?? []).filter((f) => !deliverables.some((d) => d.step === s.id && d.f.path === f.path)).map((f) => (
          <details key={s.id + f.path} id={`${s.id}-${f.path}`} className="card card-pad"><summary><b>{s.id}/{f.path}</b> <span className="caption">{f.bytes} bytes</span></summary><pre className="ab-file">{f.content_text}</pre></details>
        )))}
      </section>
    </>
  );
}
