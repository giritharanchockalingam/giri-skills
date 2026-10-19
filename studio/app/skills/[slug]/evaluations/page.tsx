import { LocalTime } from "@/components/LocalTime";
import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { can } from "@/lib/factory/roles";
import { evalGate, pct } from "@/lib/factory/release";
import { runtimeConfig } from "@/lib/factory/runtime";
import { loadVersionEvaluations } from "@/lib/db/skills";
import { saveEvalCase, deleteEvalCase } from "@/app/actions";
import { ActionForm } from "@/components/factory/ActionForm";
import { VersionBar } from "@/components/factory/VersionBar";
import { EvalRunner } from "@/components/factory/EvalRunner";
import { GateList } from "@/components/factory/GateList";
import { PassPill } from "@/components/Badge";
import { RunPill } from "@/components/factory/Pills";

export const dynamic = "force-dynamic";

export default async function EvaluationsPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string; edit?: string }> }) {
  const { slug } = await params; const { v, edit } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const { cases, runs } = await loadVersionEvaluations(d.ctx.supabase, d.version.id);
  const canEdit = can(d.ctx.role, "eval.edit"), canRun = can(d.ctx.role, "eval.run");
  const cfg = runtimeConfig();
  const editing = edit ? cases.find((c) => c.id === edit) ?? null : null;
  const runnable = !["retired", "superseded"].includes(d.version.status);
  const reason = !cfg.ok ? `Runtime not available: ${cfg.reason}` : !runnable ? `v${d.version.version} is ${d.version.status}` : cases.length === 0 ? "Add at least one case first." : !canRun ? `Your role (${d.ctx.role}) cannot run evaluations.` : null;

  return (
    <>
      <VersionBar slug={slug} view="evaluations" versions={d.versions} current={d.version} />
      <div className="two-col">
        <div className="stack min-w-0">
          <div className="card card-pad">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-1">
              <div className="h3">Evaluation cases <span className="muted font-normal">({cases.length})</span></div>
              {canEdit && !editing && <Link href={`/skills/${slug}/evaluations?v=${d.version.version}&edit=new#case-form`} className="btn btn-secondary btn-sm">Add case</Link>}
            </div>
            <p className="caption mb-3">Each case runs the version with fixed inputs and verifies deterministic checks on the result. A case passes only when every check passes. Schema validity and execution success are checked on every run; these checks are where business correctness is asserted.</p>
            <div className="list">
              {cases.map((c) => (
                <div key={c.id} className="list-row" style={{ alignItems: "flex-start" }}>
                  <div className="min-w-0">
                    <div className="name">{c.name}</div>
                    {c.notes && <div className="caption" style={{ overflowWrap: "anywhere" }}>{c.notes.slice(0, 200)}</div>}
                    <div className="mono-sm mt-1">inputs: {Object.entries(c.inputs).map(([k, val]) => `${k}=${typeof val === "object" && val && "path" in (val as object) ? `fixture:${(val as { path: string }).path}` : String(val).slice(0, 40)}`).join(", ") || "(none)"}</div>
                    <div className="mono-sm">checks: {c.checks.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(" · ")}</div>
                  </div>
                  {canEdit && <div className="flex gap-2"><Link href={`/skills/${slug}/evaluations?v=${d.version.version}&edit=${c.id}#case-form`} className="btn btn-secondary btn-sm">Edit</Link>
                    <ActionForm action={deleteEvalCase} submit="Delete" submitClass="btn btn-danger btn-sm" confirm={`Delete case “${c.name}”?`} hidden={{ case_id: c.id, slug }} /></div>}
                </div>
              ))}
              {cases.length === 0 && <p className="none">No cases yet. {canEdit ? "Add one with real inputs and the checks that prove the result is right." : "An author adds them."}</p>}
            </div>
          </div>

          {canEdit && (editing || edit === "new") && (
            <div className="card card-pad" id="case-form">
              <div className="h3 mb-3">{editing ? `Edit case — ${editing.name}` : "New case"}</div>
              <ActionForm action={saveEvalCase} submit={editing ? "Save case" : "Add case"} hidden={{ version_id: d.version.id, case_id: editing?.id ?? "", slug }}>
                <div className="form-grid form-grid-2">
                  <div className="field span-2"><label htmlFor="c-name">Name</label><input id="c-name" name="name" className="input" required maxLength={160} defaultValue={editing?.name ?? ""} placeholder="happy path — matching invoice" /></div>
                  <div className="field"><label htmlFor="c-inputs">Inputs (JSON object)</label><span className="hint">name → value. File inputs take their text content; repository fixtures as {`{"kind":"fixture","path":"evals/fixtures/x.csv"}`}.</span>
                    <textarea id="c-inputs" name="inputs" className="textarea mono" style={{ minHeight: 160 }} defaultValue={JSON.stringify(editing?.inputs ?? {}, null, 2)} spellCheck={false} /></div>
                  <div className="field"><label htmlFor="c-checks">Checks (JSON array)</label><span className="hint">{`"exit:0" · "needs_input:name" · "exists:file" · {"file":"result.json","check":"json"} · check vocabulary: exists, json, csv:[cols], sections:[...], contains:"text", max_lines:N, no_unowned_tbd, numbers_trace_to:file, cmd:"…"`}</span>
                    <textarea id="c-checks" name="checks" className="textarea mono" style={{ minHeight: 160 }} defaultValue={JSON.stringify(editing?.checks ?? ["exit:0"], null, 2)} spellCheck={false} /></div>
                  <div className="field span-2"><label htmlFor="c-notes">Reviewer notes</label><textarea id="c-notes" name="notes" className="textarea" style={{ minHeight: 64 }} maxLength={4000} defaultValue={editing?.notes ?? ""} placeholder="What this case proves and why these checks are the right evidence." /></div>
                </div>
              </ActionForm>
              <Link href={`/skills/${slug}/evaluations?v=${d.version.version}`} className="link-flame mt-3 inline-block">Cancel</Link>
            </div>
          )}

          <div className="card card-pad">
            <div className="h3 mb-1">Run evaluation</div>
            <p className="caption mb-3">Executes every case against v{d.version.version} with its current configuration (provider {d.version.manifest.model_config.provider}{d.version.manifest.model_config.provider !== "none" ? ` · ${d.version.manifest.model_config.model}` : ""}) and records the evidence with the case-set hash.</p>
            <EvalRunner versionId={d.version.id} cases={cases.length} disabled={!!reason} reason={reason} />
          </div>

          <div className="card card-pad">
            <div className="h3 mb-2">Evaluation history <span className="muted font-normal">({runs.length})</span></div>
            {runs.length === 0 ? <p className="none">No evaluation has run for this version.</p> : runs.map((r) => (
              <details key={r.id} className="disclosure" style={{ borderBottom: "1px solid var(--rule-soft)", padding: "4px 0" }} open={r.id === runs[0].id}>
                <summary><span><LocalTime iso={r.started_at} /></span><span className="muted">·</span><span className={r.status === "finished" ? (Number(r.pass_rate) >= (d.version.manifest.release_criteria.min_eval_pass_rate || 0) ? "pass" : "fail") : "muted"}>{r.status === "finished" ? `${pct(r.pass_rate)} passed` : r.status}</span>
                  <span className="caption">· {r.results.length} cases · {r.provider ?? "none"}{r.model ? ` · ${r.model}` : ""} · set {r.eval_set_hash.slice(0, 8)}{d.state?.current_eval_set_hash && r.eval_set_hash !== d.state.current_eval_set_hash ? " (outdated: cases changed since)" : ""}</span></summary>
                <div className="tablewrap mt-2"><table className="mini"><thead><tr><th>Case</th><th>Run</th><th>Checks</th><th>Detail</th></tr></thead>
                  <tbody>{r.results.map((c) => (
                    <tr key={c.case_id}><td>{c.name}</td><td>{c.run_id ? <Link href={`/runs/${c.run_id}`} className="link"><RunPill status={c.status as "failed"} small /></Link> : <span className="muted">{c.status}</span>}</td>
                      <td>{c.total ? <span className={c.passed === c.total ? "pass" : "fail"}>{c.passed}/{c.total}</span> : <span className="muted">—</span>}</td>
                      <td className="ink-2" style={{ fontSize: 13 }}>{c.error ? c.error : c.checks.filter((x) => !x.pass).map((x, k) => <div key={k}><PassPill pass={false} /> <span className="agent-check">{x.check}</span> <span className="agent-evidence">{x.evidence}</span></div>)}</td></tr>
                  ))}</tbody></table></div>
              </details>
            ))}
          </div>
        </div>
        <aside className="sidebar">
          <div className="card card-pad">
            <div className="h3 mb-2">Release gate</div>
            {d.state && <GateList gates={[evalGate(d.state)]} />}
            <p className="caption mt-2">Required pass rate comes from the manifest&apos;s release criteria (Authoring). The gate re-checks against the current case set at publish time, on the server.</p>
          </div>
          {d.version.source.kind === "repo" && <div className="card card-pad"><div className="h3 mb-1">Repository evals</div><p className="caption">The behavioural eval scorecard (trigger accuracy, judge lift, agent checks) for this repository skill is under <Link href={`/repo/${d.version.source.repo_skill}/evals/`} className="link">its repository page</Link> and <Link href="/evals/" className="link">Repo evals</Link>.</p></div>}
        </aside>
      </div>
    </>
  );
}
