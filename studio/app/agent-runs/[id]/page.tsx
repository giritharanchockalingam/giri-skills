import Link from "next/link";
import { notFound } from "next/navigation";
import { requireWorkspace, fmtDate } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";
import { PageHead } from "@/components/PageHead";
import { AgentRunDriver } from "@/components/factory/AgentRunDriver";
import { parseRef, isSkill } from "@/lib/factory/agents";
import type { AgentRunRow, AgentVersionRow } from "@/lib/factory/agentRun";

export const dynamic = "force-dynamic";
export const metadata = { title: "Agent run · Skills Factory" };

const TONE: Record<string, string> = { ok: "pill-sage", approved: "pill-sage", succeeded: "pill-sage", running: "pill-deep", awaiting_approval: "pill-hold", blocked: "pill-hold", failed: "pill-rust", needs_input: "pill-rust", skipped: "pill-none", cancelled: "pill-none" };
const LABEL: Record<string, string> = { ok: "ok", approved: "approved", succeeded: "done", running: "running", awaiting_approval: "awaiting approval", blocked: "blocked", failed: "failed", needs_input: "needs input", skipped: "skipped", cancelled: "cancelled" };

export default async function AgentRunPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ go?: string }> }) {
  const { id } = await params; const { go } = await searchParams;
  const ctx = await requireWorkspace();
  const { data: r } = await ctx.supabase.from("sf_agent_runs").select("*").eq("id", id).eq("workspace_id", ctx.workspace.id).maybeSingle();
  if (!r) notFound();
  const run = r as AgentRunRow;
  const { data: v } = await ctx.supabase.from("sf_agent_versions").select("*, sf_agents!inner(slug, name)").eq("id", run.agent_version_id).single();
  const version = v as AgentVersionRow & { sf_agents: { slug: string; name: string } };
  const spec = version.spec;
  const waiting = run.steps.find((s) => s.status === "awaiting_approval");
  const deliverables = (spec.outputs ?? []).map((ref) => { const p = parseRef(ref); if (p?.kind !== "step") return null; const rec = run.steps.find((s) => s.id === p.step); const f = rec?.files?.find((x) => x.path === p.file); return f ? { step: p.step, f } : null; }).filter(Boolean) as { step: string; f: { path: string; bytes: number; content_text: string | null } }[];

  return (
    <>
      <PageHead eyebrow={`Agent run · ${version.sf_agents.slug} v${version.version}`} title={version.sf_agents.name} em=""
        lead={<><span className={`pill ${TONE[run.status]}`}>{LABEL[run.status]}</span> {run.error && <span className="caption"> {run.error}</span>}</>}
        caption={<>Started {fmtDate(run.created_at)} · {run.steps.filter((s) => s.status === "ok" || s.status === "approved").length}/{spec.steps.length} steps{run.cost_usd != null ? ` · model cost ≈$${Number(run.cost_usd).toFixed(4)}` : ""} · <Link href={`/agents/${version.sf_agents.slug}?v=${version.version}`} className="link">configuration</Link></>} />
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
