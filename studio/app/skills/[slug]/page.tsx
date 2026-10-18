import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { evalGate, approvalGate, pct } from "@/lib/factory/release";
import { fmtDate } from "@/lib/factory/db";
import { VersionBar } from "@/components/factory/VersionBar";
import { GateList } from "@/components/factory/GateList";
import { RunPill } from "@/components/factory/Pills";
import type { RunStatus } from "@/lib/factory/db";

export const dynamic = "force-dynamic";
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) { const { slug } = await params; return { title: `${slug} · Skills Factory` }; }

/** Overview: what/when, the contract (inputs · outputs) and the evidence for this version. Steps, model, limits,
 *  needs and the version list live under Instructions, Files, Activity and Release. */
export default async function SkillOverview({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const m = d.version.manifest;
  const vq = `?v=${d.version.version}`;
  const { data: lastRun } = await d.ctx.supabase.from("sf_runs").select("id, status, created_at").eq("version_id", d.version.id).order("created_at", { ascending: false }).limit(1).maybeSingle();

  return (
    <>
      <VersionBar slug={slug} view="" versions={d.versions} current={d.version} />
      <div className="detail-grid">
        <div className="stack min-w-0">
          <div className="card card-pad">
            <div className="h3">What it does · when to use it</div>
            <p className="tab-lead mt-2">{d.skill.purpose || <span className="none">No purpose written yet — add one under Instructions.</span>}</p>
            <dl className="kv mt-3">
              <dt>When to use it</dt><dd>{d.skill.usage_guidance || <span className="none">not stated</span>}</dd>
              <dt>Intended users</dt><dd>{d.skill.intended_users || <span className="none">not stated</span>}</dd>
              <dt>Runs</dt><dd>{m.run.length === 0 ? <span className="none">no steps yet — define one under Instructions</span> : <>{m.run.length} step{m.run.length === 1 ? "" : "s"} · {m.model_config.provider === "none" ? "no model (deterministic scripts)" : `${m.model_config.provider} · ${m.model_config.model}`} · {m.limits.timeout_s}s deadline</>}</dd>
            </dl>
          </div>
          <div className="card card-pad">
            <div className="h3">Inputs <span className="muted font-normal">({m.inputs.length})</span></div>
            {m.inputs.length === 0 ? <p className="none mt-2">No inputs declared.</p> : (
              <div className="tablewrap"><table className="mini agent-inputs mt-2"><thead><tr><th>Name</th><th>Required</th><th>Type</th></tr></thead>
                <tbody>{m.inputs.map((i) => <tr key={i.name}><td><code>{i.name}</code></td><td>{i.required ? <span className="agent-req">yes</span> : <span className="muted">no</span>}</td><td className="muted">{i.type}{i.schema ? " · schema" : ""}</td></tr>)}</tbody></table></div>
            )}
            <div className="h3 mt-5">Outputs <span className="muted font-normal">({m.outputs.length})</span></div>
            {m.outputs.length === 0 ? <p className="none mt-2">None declared.</p> : (
              <ul className="agent-list mt-2">
                {m.outputs.map((o) => <li key={o.path}><code>{o.path}</code><span className="caption">{o.checks.length} check{o.checks.length === 1 ? "" : "s"}{o.schema ? " · JSON schema" : ""}</span></li>)}
              </ul>
            )}
          </div>
        </div>
        <aside className="sidebar">
          <div className="card card-pad">
            <div className="h3 mb-2">Evidence · v{d.version.version}</div>
            {d.state ? <GateList gates={[evalGate(d.state), approvalGate(d.state)]} /> : <p className="none">No release state.</p>}
            <dl className="kv mt-3">
              <dt>Evaluation</dt><dd>{d.state?.latest_eval_run_id ? <Link href={`/skills/${slug}/evaluations/${vq}`} className="link">{pct(d.state.latest_eval_pass_rate)} on {d.state.eval_case_count} case{d.state.eval_case_count === 1 ? "" : "s"}</Link> : <span className="none">{d.state?.eval_case_count ?? 0} case(s), not run</span>}</dd>
              <dt>Runs</dt><dd>{lastRun ? <><Link href={`/runs/${lastRun.id}`} className="link"><RunPill status={lastRun.status as RunStatus} small /></Link> <span className="caption">{fmtDate(lastRun.created_at)} · {d.runCount} total</span></> : <span className="none">never run</span>}</dd>
              <dt>Release</dt><dd><Link href={`/skills/${slug}/release/${vq}`} className="link-flame">Gates and lifecycle →</Link></dd>
            </dl>
          </div>
        </aside>
      </div>
    </>
  );
}
