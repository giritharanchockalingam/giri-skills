import { skillTitle } from "@/lib/names";
import { modelLabel } from "@/lib/modelLabel";
import { LocalTime } from "@/components/LocalTime";
import Link from "next/link";
import { notFound } from "next/navigation";
import {requireWorkspace, fmtMs, fmtUsd } from "@/lib/factory/db";
import { getRunWithVersion } from "@/lib/db/runs";
import { cancelRun } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { RunPill, VersionPill } from "@/components/factory/Pills";
import { PassPill } from "@/components/Badge";
import { RunOutputs } from "@/components/factory/RunOutputs";

export const dynamic = "force-dynamic";
export const metadata = { title: "Run · Skills Factory" };

interface Step { step: string; kind: string; ok: boolean; exit?: number; duration_s?: number; skipped?: boolean; skipped_reason?: string; reason?: string; error?: string; provider?: string }
interface Check { check: string; pass: boolean; evidence: string; path: string }
interface Factory { contract?: { ok: boolean; problems: { path: string; message: string }[] }; provider?: { requested: string; used: string; available: boolean; note: string }; case_checks?: { check: string; pass: boolean; evidence: string }[] | null; runtime?: Record<string, string>; needs_input?: { missing: { name: string; question: string }[] } | null; exit_code?: number | null }

export default async function RunPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ from?: string }> }) {
  const { id } = await params; const { from } = await searchParams;
  const ctx = await requireWorkspace();
  const run = await getRunWithVersion(ctx.supabase, ctx.workspace.id, id);
  if (!run) notFound();
  const vinfo = run.sf_skill_versions;
  const rj = (run.run_json ?? {}) as { steps?: Step[]; checks?: Check[]; assumptions?: Record<string, string>; inputs?: Record<string, string>; out?: string; factory?: Factory };
  const f = rj.factory ?? {};
  const out = rj.out ?? "";
  const rel = (p: string) => (out && p.startsWith(out + "/") ? p.slice(out.length + 1) : p);
  const headline = run.status === "succeeded" ? "Succeeded — every step ran, every check passed and the output contract holds."
    : run.status === "needs_input" ? `Needs input — ${run.error}` : run.status === "timeout" ? `Timed out — ${run.error}` : run.status === "cancelled" ? "Cancelled before it started."
    : run.status === "running" || run.status === "queued" ? "In progress." : `Failed — ${run.error ?? "see steps and checks"}`;
  const tone = run.status === "succeeded" ? "sage" : run.status === "needs_input" || run.status === "running" || run.status === "queued" ? "hold" : "rust";
  const usage = run.usage as { input_tokens?: number; output_tokens?: number; calls?: number; retries?: number; source?: string } | null;

  return (
    <>
      <div className="page-head" style={{ marginBottom: 24 }}>
        <nav className="caption" aria-label="Breadcrumb">
          {from === "test" ? <Link href={`/skills/${vinfo.sf_skills.slug}/test?v=${vinfo.version}`} className="link">← Back to Test</Link> : <Link href="/activity" className="link">Activity</Link>} <span aria-hidden="true">›</span> run {id.slice(0, 8)}
        </nav>
        <h1 className="h1" style={{ margin: "8px 0 10px" }}>{skillTitle(vinfo.sf_skills.name)} <span className="muted" style={{ fontSize: "0.6em" }}>v{vinfo.version}</span></h1>
        <div className="flex flex-wrap items-center gap-3"><RunPill status={run.status} /><VersionPill status={vinfo.status} small /><span className="caption">{run.source} · <LocalTime iso={run.created_at} /> · manifest {vinfo.manifest_hash.slice(0, 12)}…</span></div>
      </div>
      <div className={`run-banner run-banner-${tone}`} role="status">{headline}</div>
      {run.status === "queued" && <div className="mt-3"><ActionForm action={cancelRun} submit="Cancel run" submitClass="btn btn-danger" hidden={{ run_id: id }} /></div>}

      <div className="two-col mt-6">
        <div className="stack min-w-0">
          {f.needs_input?.missing?.length ? (
            <div className="card card-pad"><div className="h3 mb-2">Missing inputs</div><div className="tablewrap"><table className="mini"><thead><tr><th>Input</th><th>What it is</th></tr></thead><tbody>{f.needs_input.missing.map((m) => <tr key={m.name}><td><code>{m.name}</code></td><td className="ink-2">{m.question}</td></tr>)}</tbody></table></div></div>
          ) : null}
          <div className="card card-pad">
            <div className="h3 mb-2">Steps <span className="muted font-normal">({rj.steps?.length ?? 0})</span></div>
            {rj.steps?.length ? (
              <div className="run-tablewrap"><table className="mini run-steps"><thead><tr><th>Step</th><th>Kind</th><th>Status</th><th>Exit</th><th>Duration</th><th>Detail</th></tr></thead>
                <tbody>{rj.steps.map((s) => <tr key={s.step}><td><code>{s.step}</code></td><td><span className={`agent-kind agent-kind-${s.kind}`}>{s.kind}</span></td><td>{s.skipped ? <span className="na-pill">skipped</span> : <PassPill pass={s.ok} />}</td><td className="muted">{s.exit ?? "—"}</td><td className="muted tnum">{s.duration_s != null ? `${s.duration_s}s` : "—"}</td><td className="ink-2" style={{ whiteSpace: "normal" }}>{s.skipped ? (s.skipped_reason ?? s.reason) : s.ok ? (s.provider ? (s.provider === "dry" ? "no model (scripts only)" : `model provider ${s.provider}`) : "") : s.error}</td></tr>)}</tbody></table></div>
            ) : <p className="none">No steps were recorded{run.error ? ` — ${run.error}` : ""}.</p>}
          </div>
          <div className="card card-pad">
            <div className="h3 mb-2">Checks <span className="muted font-normal">({rj.checks?.filter((c) => c.pass).length ?? 0} of {rj.checks?.length ?? 0} passed)</span></div>
            {rj.checks?.length ? (
              <div className="run-tablewrap"><table className="mini run-checks"><thead><tr><th>File</th><th>Check</th><th>Result</th><th>Evidence</th></tr></thead>
                <tbody>{rj.checks.map((c, k) => <tr key={k} className={c.pass ? "" : "run-row-fail"}><td><code>{rel(c.path).split("/").pop()}</code></td><td className="agent-check">{c.check.replaceAll(out + "/", "")}</td><td><PassPill pass={c.pass} /></td><td className="agent-evidence">{c.evidence.replaceAll(out + "/", "")}</td></tr>)}</tbody></table></div>
            ) : <p className="none">No checks were evaluated.</p>}
            {f.contract && <div className={`notice mt-3 ${f.contract.ok ? "notice-ok" : "notice-err"}`}>Output contract: {f.contract.ok ? "every declared output was produced and valid." : f.contract.problems.map((p) => `${p.path} ${p.message}`).join("; ")}</div>}
            {f.case_checks && <div className="mt-4"><div className="h3" style={{ fontSize: 14 }}>Evaluation-case checks</div><ul className="agent-checks mt-2">{f.case_checks.map((c, k) => <li key={k}><PassPill pass={c.pass} /><div><div className="agent-check">{c.check}</div><div className="agent-evidence">{c.evidence}</div></div></li>)}</ul></div>}
          </div>
          <RunOutputs outputs={run.outputs} logs={run.logs} runJson={run.run_json} />
        </div>
        <aside className="sidebar">
          <div className="card card-pad">
            <div className="h3 mb-2">Execution</div>
            <dl className="kv">
              <dt>Provider</dt><dd>{run.provider ?? "—"}{f.provider?.note && <div className="caption">{f.provider.note}</div>}</dd>
              <dt>Model</dt><dd>{run.model ? <span title={`model id: ${run.model}`}>{modelLabel(run.model)} <span className="caption">· <code>{run.model}</code></span></span> : <span className="muted">none used</span>}</dd>
              <dt>Usage</dt><dd>{usage?.calls ? `${usage.input_tokens?.toLocaleString()} in · ${usage.output_tokens?.toLocaleString()} out · ${usage.calls} call${usage.calls === 1 ? "" : "s"}${usage.retries ? ` · ${usage.retries} retr${usage.retries === 1 ? "y" : "ies"}` : ""}` : <span className="muted">no model calls</span>}{usage?.source && <div className="caption">{usage.source}</div>}</dd>
              <dt>Cost</dt><dd>{run.cost_usd != null ? <>{fmtUsd(run.cost_usd, run.cost_is_estimate)} <span className="caption">({run.cost_is_estimate ? "estimate: provider tokens × price table" : "measured"})</span></> : <span className="muted">— (no billable calls)</span>}</dd>
              <dt>Duration</dt><dd>{fmtMs(run.duration_ms)}</dd>
              <dt>Started</dt><dd><LocalTime iso={run.started_at} /></dd>
              <dt>Finished</dt><dd><LocalTime iso={run.finished_at} /></dd>
              <dt>Exit code</dt><dd>{f.exit_code ?? "—"}</dd>
              <dt>Runtime</dt><dd className="mono-sm">{f.runtime ? `${f.runtime.runtime_version} · python ${f.runtime.python} · ${f.runtime.runner_version}` : "—"}</dd>
              <dt>Invoked by</dt><dd>{run.api_key_id ? `API key ${run.api_key_id.slice(0, 8)}…` : run.invoked_by === ctx.user.id ? "you" : run.invoked_by?.slice(0, 8) ?? "—"}</dd>
              <dt>Idempotency key</dt><dd className="mono-sm">{run.idempotency_key ?? "—"}</dd>
            </dl>
          </div>
          <div className="card card-pad">
            <div className="h3 mb-2">Inputs</div>
            <p className="caption mb-2">Reference only — names, sizes and content hashes; raw inputs are not stored.</p>
            <div className="list">{(run.inputs_ref as { name: string; kind: string; bytes: number; sha256: string | null; value?: string }[]).map((i) => (
              <div key={i.name} className="list-row" style={{ display: "block" }}><code>{i.name}</code> <span className="caption">{i.kind}{i.bytes ? ` · ${i.bytes} B` : ""}</span>{i.value != null && <div className="mono-sm">{i.value}</div>}{i.sha256 && <div className="mono-sm">sha256 {i.sha256.slice(0, 16)}…</div>}</div>
            ))}{(run.inputs_ref as unknown[]).length === 0 && <p className="none">none</p>}</div>
            {rj.assumptions && Object.keys(rj.assumptions).length > 0 && <div className="mt-3"><div className="caption">Assumptions</div>{Object.values(rj.assumptions).map((a) => <div key={a} className="mono-sm">{a}</div>)}</div>}
          </div>
        </aside>
      </div>
    </>
  );
}
