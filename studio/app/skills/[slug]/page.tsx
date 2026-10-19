import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { evalGate, approvalGate, pct } from "@/lib/factory/release";
import { fmtDate } from "@/lib/factory/db";
import { VersionBar } from "@/components/factory/VersionBar";
import { GateList } from "@/components/factory/GateList";
import { RunPill } from "@/components/factory/Pills";
import type { RunStatus } from "@/lib/factory/db";
import { getLastVersionRun } from "@/lib/db/runs";

export const dynamic = "force-dynamic";
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) { const { slug } = await params; return { title: `${slug} · Skills Factory` }; }

/** Overview: one screen of facts — source, runs, contract (inputs · outputs) and evidence. The purpose text is in the header. */
export default async function SkillOverview({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const { slug } = await params; const { v } = await searchParams;
  const d = await loadSkillPage(slug, v ?? null);
  const m = d.version.manifest;
  const vq = `?v=${d.version.version}`;
  const lastRun = await getLastVersionRun(d.ctx.supabase, d.version.id);

  return (
    <>
      <VersionBar slug={slug} view="" versions={d.versions} current={d.version} />
      <div className="detail-grid">
        <div className="stack min-w-0">
          <div className="card card-pad">
            <dl className="kv">
              <dt>Source</dt><dd>{d.version.source.kind === "repo" ? <>repository <code>{d.version.source.repo_skill}</code></> : "authored in this workspace"}</dd>
              {d.skill.intended_users && <><dt>For</dt><dd>{d.skill.intended_users}</dd></>}
              <dt>Runs</dt><dd>{m.run.length === 0 ? <span className="none">no steps yet — define one under Instructions</span> : <>{m.run.length} step{m.run.length === 1 ? "" : "s"} · {m.model_config.provider === "none" ? "scripts only, no model" : `${m.model_config.provider} · ${m.model_config.model}`} · {m.limits.timeout_s}s limit</>}</dd>
              <dt>Inputs</dt><dd>{m.inputs.length === 0 ? <span className="none">none</span> : <span className="chip-group">{m.inputs.map((i) => <span key={i.name} className="chip" style={{ cursor: "default" }}><code>{i.name}</code>{i.required && <span className="agent-req">*</span>}<span className="muted"> {i.type}</span></span>)}<span className="caption">* required</span></span>}</dd>
              <dt>Outputs</dt><dd>{m.outputs.length === 0 ? <span className="none">none</span> : <span className="chip-group">{m.outputs.map((o) => <span key={o.path} className="chip" style={{ cursor: "default" }}><code>{o.path.replace(/^\{out\}\//, "")}</code><span className="muted"> · {o.checks.length} check{o.checks.length === 1 ? "" : "s"}</span></span>)}</span>}</dd>
            </dl>
          </div>
        </div>
        <aside className="sidebar">
          <div className="card card-pad">
            <div className="h3 mb-2">Evidence · v{d.version.version}</div>
            {d.state ? <GateList compact gates={[evalGate(d.state), approvalGate(d.state)]} /> : <p className="none">No release state.</p>}
            <dl className="kv mt-3">
              <dt>Evaluation</dt><dd>{d.state?.latest_eval_run_id ? <Link href={`/skills/${slug}/evaluations/${vq}`} className="link">{pct(d.state.latest_eval_pass_rate)} on {d.state.eval_case_count} case{d.state.eval_case_count === 1 ? "" : "s"}</Link> : <span className="none">{d.state?.eval_case_count ?? 0} cases, not run</span>}</dd>
              <dt>Runs</dt><dd>{lastRun ? <><Link href={`/runs/${lastRun.id}`} className="link"><RunPill status={lastRun.status as RunStatus} small /></Link> <span className="caption">{fmtDate(lastRun.created_at)} · {d.runCount} total</span></> : <span className="none">never run</span>}</dd>
              <dt>Next</dt><dd><Link href={`/skills/${slug}/release/${vq}`} className="link-flame">Release gates →</Link></dd>
            </dl>
          </div>
        </aside>
      </div>
    </>
  );
}
