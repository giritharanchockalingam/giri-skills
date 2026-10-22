import Link from "next/link";
import { notFound } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead, SectionHead } from "@/components/PageHead";
import { LocalTime } from "@/components/LocalTime";
import { CopyButton } from "@/components/CopyButton";
import { ActionForm } from "@/components/factory/ActionForm";
import { DeliveryPill, StagePill, VerdictPill } from "@/components/factory/DeliveryPills";
import { approveDelivery } from "@/app/deliverActions";
import { awaitingStage, canApproveStage, deliverCommand } from "@/lib/delivery/core";
import { pipelineByName } from "@/lib/delivery/pipelines";
import { portalUrl } from "@/lib/delivery/config";
import { getDeliveryRun, listDeliveryApprovals, listUserRoleSlugs, memberEmails } from "@/lib/db/delivery";

export const metadata = { title: "Delivery run · Skills Factory" };
export const dynamic = "force-dynamic";

const PROFILE_KEYS = ["flavour", "framework", "package_manager", "test_runner", "e2e", "deploy_target", "migrations_dir", "monorepo_root"];

export default async function DeliveryRunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ctx = await requireWorkspace();
  const run = await getDeliveryRun(ctx.supabase, ctx.workspace.id, id);
  if (!run) notFound();
  const [approvals, job, emails] = await Promise.all([listDeliveryApprovals(ctx.supabase, run.id), listUserRoleSlugs(ctx.supabase, ctx.workspace.id, ctx.user.id), memberEmails(ctx.supabase, ctx.workspace.id)]);
  const template = pipelineByName(run.pipeline);
  const command = deliverCommand(run, await portalUrl());
  const waiting = awaitingStage(run);
  const mayApprove = waiting ? canApproveStage({ member: ctx.role, job }, waiting) : false;
  const approvedBy = new Map(approvals.map((a) => [a.stage_id, a]));
  const done = run.stages.filter((s) => s.status === "succeeded").length;
  const profile = run.stack_profile ?? null;
  const headline = run.status === "succeeded" ? "Delivered — every stage passed its gate; merge the pull request to ship."
    : run.status === "awaiting_approval" ? `Waiting for a person: ${waiting?.role ?? "the owning role"} must approve “${waiting?.id}” before the executor continues.`
    : run.status === "blocked" ? `Stopped by a gate at “${run.stage}” — a verdict, not a malfunction. ${run.error ?? ""}`
    : run.status === "failed" ? `Failed at “${run.stage}”. ${run.error ?? ""}`
    : run.status === "queued" ? (run.executor === "github-actions" && !run.executor_ref?.startsWith("https://") ? run.executor_ref || "Queued: waiting for an executor." : "Queued: the executor has not posted its first stage yet.")
    : `Running “${run.stage}”.`;

  return (
    <>
      <PageHead eyebrow={`Build · deliver · ${run.pipeline} v${run.pipeline_version}`} title={template?.title ?? run.pipeline} em="" after=""
        lead={<><DeliveryPill status={run.status} /> <span className="caption">{done}/{run.stages.length} stages · {run.mode} · runs on {run.executor}</span></>}
        caption={<>Started <LocalTime iso={run.created_at} /> by {run.created_by ? emails.get(run.created_by) ?? run.created_by : "an API key"} · <span className="mono-sm">{run.repo}{run.ref ? `@${run.ref}` : ""}</span> · <Link className="link" href="/deliver">all runs</Link> · <a className="link" href={`/api/delivery-runs/${run.id}?download=1`}>run.json</a></>} />

      <div className="card card-pad run-answer mb-5">
        <div className="h3" style={{ marginTop: 0 }}>{headline}</div>
        <p className="caption" style={{ whiteSpace: "pre-wrap" }}>{run.request}</p>
        {run.pr?.url && <p><a className="btn btn-secondary" href={run.pr.url} target="_blank" rel="noreferrer">Pull request #{run.pr.number ?? ""}{run.pr.head_sha ? ` · ${run.pr.head_sha.slice(0, 7)}` : ""}</a></p>}
        {run.executor_ref?.startsWith("https://") && <p className="caption">Executor: <a className="link" href={run.executor_ref} target="_blank" rel="noreferrer">{run.executor_ref}</a></p>}
        {run.executor !== "github-actions" && run.status !== "succeeded" && (
          <div className="stack-sm">
            <p className="caption">Run the executor from your checkout of the library; it posts each stage back here with your API key in <code>SF_API_KEY</code>:</p>
            <pre className="mono-sm" style={{ whiteSpace: "pre-wrap" }}>{command}</pre>
            <div><CopyButton text={command} /></div>
          </div>
        )}
        {waiting && (
          <div className="card card-pad stack-sm mt-3">
            <div className="h3" style={{ marginTop: 0 }}>Approval · {waiting.id} · {waiting.role}</div>
            {mayApprove ? (
              <ActionForm action={approveDelivery} submit="Approve and continue" hidden={{ run_id: run.id, stage_id: waiting.id }}>
                <textarea name="note" className="textarea" style={{ minHeight: 60 }} placeholder="What you checked (recorded with your approval)" />
              </ActionForm>
            ) : <p className="caption">A member assigned to the <b>{waiting.role}</b> role (or an admin) approves this stage. Your job roles: {job.length ? job.join(", ") : "none"}.</p>}
          </div>
        )}
      </div>

      <SectionHead title="Stack" em="profile" caption="Read from the repository before stage 1 and passed to every stage; never guessed." />
      {profile ? (
        <dl className="kv card card-pad mb-5">
          {PROFILE_KEYS.filter((k) => k in profile).map((k) => <div key={k}><dt>{k}</dt><dd className="mono-sm">{String((profile as Record<string, unknown>)[k] ?? "—")}</dd></div>)}
          {!!profile.baselines && typeof profile.baselines === "object" && <div><dt>baselines</dt><dd className="mono-sm">{Object.keys(profile.baselines as object).join(", ") || "none"}</dd></div>}
        </dl>
      ) : <p className="caption mb-5">Not posted yet — the executor records it with the first stage.</p>}

      <SectionHead title="Stages" caption="Stage · role · gate · verdict · evidence (sha256 of every file) · who approved." />
      <div className="card tablewrap mb-5">
        <table className="tbl">
          <thead><tr><th>Stage</th><th>Role</th><th>Status</th><th>Gate</th><th>Verdict</th><th>Evidence</th><th>Approved by</th><th>Finished</th></tr></thead>
          <tbody>
            {run.stages.map((s) => {
              const a = approvedBy.get(s.id);
              const gateKind = s.gate?.kind ?? (template?.stages.find((t) => t.id === s.id)?.gate as { kind?: string } | undefined)?.kind ?? "—";
              return (
                <tr key={s.id}>
                  <td><b>{s.id}</b><div className="caption">{s.adlc_stage}</div></td>
                  <td className="mono-sm">{s.role || "—"}</td>
                  <td><StagePill status={s.status} small /></td>
                  <td className="mono-sm">{gateKind}{s.gate?.detail ? <div className="caption">{s.gate.detail}</div> : null}</td>
                  <td><VerdictPill verdict={s.gate?.verdict} /></td>
                  <td>{s.evidence?.length ? <ul className="mono-sm" style={{ margin: 0, paddingLeft: 16 }}>{s.evidence.map((e) => <li key={e.path} title={e.sha256}>{e.path} <span className="caption">{e.sha256.slice(0, 12)}… · {e.bytes} B</span></li>)}</ul> : <span className="caption">—</span>}</td>
                  <td>{a ? <>{emails.get(a.approved_by) ?? a.approved_by}{a.note ? <div className="caption">{a.note}</div> : null}</> : <span className="caption">—</span>}</td>
                  <td><LocalTime iso={s.finished_at ?? null} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {run.error && run.status !== "blocked" && <div className="notice notice-err" role="alert">{run.error}</div>}
    </>
  );
}
