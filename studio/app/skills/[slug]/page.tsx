import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { evalGate, approvalGate, nextAction, pct } from "@/lib/factory/release";
import { requirements } from "@/lib/factory/manifest";
import { can } from "@/lib/factory/roles";
import { fmtDate, type ConnectionRow } from "@/lib/factory/db";
import { VersionBar } from "@/components/factory/VersionBar";
import { VersionPill } from "@/components/factory/Pills";
import { GateList } from "@/components/factory/GateList";

export const dynamic = "force-dynamic";
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) { const { slug } = await params; return { title: `${slug} · Skills Factory` }; }

export default async function SkillSummary({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const m = d.version.manifest;
  const req = requirements(m);
  const { data: conns } = await d.ctx.supabase.from("sf_connections").select("*").eq("workspace_id", d.ctx.workspace.id);
  const connections = (conns ?? []) as ConnectionRow[];
  const serverKey = Boolean(process.env.ANTHROPIC_API_KEY);
  const na = d.state ? nextAction(d.state, d.runCount > 0) : null;
  const href = (a: string) => a === "edit" ? `/skills/${slug}/authoring?v=${d.version.version}` : a === "test" ? `/skills/${slug}/test?v=${d.version.version}` : a === "add_cases" || a === "run_eval" ? `/skills/${slug}/evaluations?v=${d.version.version}` : `/skills/${slug}/release?v=${d.version.version}`;
  const allowed = !na ? false : na.who === "reviewer" ? can(d.ctx.role, "version.review") : na.action === "new_draft" ? can(d.ctx.role, "version.create") : na.action === "publish" ? can(d.ctx.role, "version.publish") : can(d.ctx.role, "version.edit");
  const { data: lastRun } = await d.ctx.supabase.from("sf_runs").select("id, status, created_at").eq("version_id", d.version.id).order("created_at", { ascending: false }).limit(1).maybeSingle();

  return (
    <>
      <VersionBar slug={slug} view="" versions={d.versions} current={d.version}
        right={na && (allowed ? <Link href={href(na.action)} className="btn btn-primary">{na.label}</Link> : <span className="caption">Next: {na.label} ({na.who})</span>)} />
      <div className="two-col">
        <div className="stack min-w-0">
          <div className="card card-pad">
            <div className="h3">What it does</div>
            <p className="sub mt-2" style={{ maxWidth: "none" }}>{d.skill.purpose || <span className="none">No purpose written yet — add one in Authoring.</span>}</p>
            <dl className="kv mt-4">
              <dt>Intended users</dt><dd>{d.skill.intended_users || <span className="none">not stated</span>}</dd>
              <dt>When to use it</dt><dd>{d.skill.usage_guidance || <span className="none">not stated</span>}</dd>
              <dt>Model</dt><dd>{m.model_config.provider === "none" ? "No model — deterministic scripts only" : `${m.model_config.provider} · ${m.model_config.model} · temperature ${m.model_config.temperature}`}</dd>
              <dt>Limits</dt><dd>{m.limits.timeout_s}s deadline · {m.limits.max_retries} retries · {m.limits.max_tokens.toLocaleString()} tokens{m.limits.max_cost_usd != null ? ` · ≤ $${m.limits.max_cost_usd}` : ""}</dd>
            </dl>
          </div>
          <div className="card card-pad">
            <div className="h3">Inputs <span className="muted font-normal">({m.inputs.length})</span></div>
            {m.inputs.length === 0 ? <p className="none mt-2">No inputs declared.</p> : (
              <div className="tablewrap"><table className="mini agent-inputs mt-2"><thead><tr><th>Name</th><th>Required</th><th>Type</th><th>Where it comes from</th></tr></thead>
                <tbody>{m.inputs.map((i) => <tr key={i.name}><td><code>{i.name}</code></td><td>{i.required ? <span className="agent-req">yes</span> : <span className="muted">no</span>}</td><td className="muted">{i.type}</td><td className="ink-2">{i.from || (i.default != null ? <>default <code>{i.default}</code></> : "—")}{i.schema && <span className="caption"> · schema-validated</span>}</td></tr>)}</tbody></table></div>
            )}
            <div className="h3 mt-6">Outputs <span className="muted font-normal">({m.outputs.length})</span></div>
            <ul className="agent-list mt-2">
              {m.outputs.map((o) => <li key={o.path}><div className="min-w-0"><code>{o.path}</code><div className="caption" style={{ overflowWrap: "anywhere" }}>checks: {o.checks.join(", ") || "none"}{o.schema ? " · JSON schema" : ""}</div></div></li>)}
            </ul>
            <p className="caption mt-3">After every run the output contract is validated: a run whose declared outputs are missing or fail their checks is recorded as failed, never as success.</p>
          </div>
          <div className="card card-pad">
            <div className="h3">Steps <span className="muted font-normal">({m.run.length})</span></div>
            {m.run.length === 0 ? <p className="none mt-2">No steps yet — this skill cannot run until Authoring defines at least one script or llm step.</p> : (
              <ol className="agent-list mt-2">{m.run.map((s) => <li key={s.step}><span className={`agent-kind agent-kind-${s.kind}`}>{s.kind}</span><code style={{ overflowWrap: "anywhere" }}>{s.kind === "script" ? s.cmd : `fill ${s.template} → ${s.out}`}</code></li>)}</ol>
            )}
          </div>
        </div>
        <aside className="sidebar">
          <div className="card card-pad">
            <div className="h3 mb-2">Evidence</div>
            {d.state ? <GateList gates={[evalGate(d.state), approvalGate(d.state)]} /> : <p className="none">No release state.</p>}
            <dl className="kv mt-3">
              <dt>Latest run</dt><dd>{lastRun ? <Link href={`/runs/${lastRun.id}`} className="link">{lastRun.status} · {fmtDate(lastRun.created_at)}</Link> : <span className="none">never run</span>}</dd>
              <dt>Evaluation</dt><dd>{d.state?.latest_eval_run_id ? `${pct(d.state.latest_eval_pass_rate)} on ${d.state.eval_case_count} case${d.state.eval_case_count === 1 ? "" : "s"} · ${fmtDate(d.state.latest_eval_at)}` : `${d.state?.eval_case_count ?? 0} case(s), not run`}</dd>
            </dl>
            <Link href={`/skills/${slug}/release?v=${d.version.version}`} className="link-flame mt-3 inline-block">Release view →</Link>
          </div>
          <div className="card card-pad">
            <div className="h3 mb-2">Needs</div>
            <dl className="kv">
              <dt>Tools</dt><dd>{req.tools.length ? req.tools.join(", ") : "none"}</dd>
              <dt>Connections</dt>
              <dd>{req.connections.length === 0 ? "none" : req.connections.map((c) => {
                const row = connections.find((x) => x.name === c);
                const ok = c === "anthropic" ? serverKey : row?.status === "configured";
                return <div key={c}><code>{c}</code> — {ok ? <span className="pass">configured</span> : <span className="fail">not configured</span>}{c === "anthropic" && !serverKey && <span className="caption"> (ANTHROPIC_API_KEY missing on the server; llm steps will be skipped)</span>}</div>;
              })}</dd>
              <dt>Permissions</dt><dd>Consumers run published versions; authors run any version.</dd>
            </dl>
            {can(d.ctx.role, "admin.connections") && <Link href="/admin#connections" className="link-flame mt-3 inline-block">Manage connections →</Link>}
          </div>
          <div className="card card-pad">
            <div className="h3 mb-2">Versions</div>
            <div className="list">{d.versions.map((x) => (
              <Link key={x.id} href={`/skills/${slug}?v=${x.version}`} className="list-row row-link"><span className="name">v{x.version} <span className="caption">{x.change_note.slice(0, 60)}</span></span><VersionPill status={x.status} small /></Link>
            ))}</div>
          </div>
        </aside>
      </div>
    </>
  );
}
