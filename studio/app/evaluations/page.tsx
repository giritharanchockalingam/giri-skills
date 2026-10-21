import { skillTitle } from "@/lib/names";
import { modelLabel } from "@/lib/modelLabel";
import { LocalTime } from "@/components/LocalTime";
import Link from "next/link";
import {requireWorkspace } from "@/lib/factory/db";
import { loadEvaluationsOverview } from "@/lib/db/skills";
import { evalGate, approvalGate, pct } from "@/lib/factory/release";
import { meta } from "@/lib/data";
import { PageHead, SectionHead } from "@/components/PageHead";
import { VersionPill } from "@/components/factory/Pills";

export const metadata = { title: "Evaluations · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function EvaluationsPage() {
  const ctx = await requireWorkspace();
  const { skills, states } = await loadEvaluationsOverview(ctx.supabase, ctx.workspace.id);
  const rows = states.map((s) => ({ s, skill: skills.find((k) => k.id === s.skill_id)! })).filter((r) => r.skill).sort((a, b) => a.skill.name.localeCompare(b.skill.name) || b.s.version - a.s.version);
  const evaluated = rows.filter((r) => r.s.latest_eval_run_id).length;
  const gated = rows.filter((r) => r.s.eval_gate_met).length;
  const current = rows.filter((r) => r.s.latest_eval_run_id && r.s.eval_current);
  const cases = current.reduce((n, r) => n + r.s.eval_case_count, 0);
  const perfect = current.filter((r) => Number(r.s.latest_eval_pass_rate) === 1).length;
  return (
    <>
      <PageHead eyebrow={`Evaluations · ${ctx.workspace.name}`} title="Quality" em="evidence" after="."
        lead={rows.length ? `${rows.length} active version${rows.length === 1 ? "" : "s"}: ${evaluated} evaluated, ${gated} meet their release gate. ${perfect} of ${current.length} current evaluations pass every case (${cases} cases in all).` : "No versions to evaluate yet."}
        caption="Pass rate = cases whose checks all passed ÷ cases, on the exact version and case set recorded with the run. Cases are each skill's own test inputs (typically a few per skill), so 100% means every check passed on those cases — not that the skill is right on every input. Lift and trigger, measured separately, are in the library scorecard."
        note={<><Link href="/evals/" className="link-flame">Repo evals (scorecard of the repository skills) →</Link> · <Link href="/findings/" className="link-flame">Findings →</Link></>} />
      <div className="card">
        {rows.length === 0 ? <div className="empty"><div className="none">Nothing to show yet.</div><p className="caption">Create or import a skill, add evaluation cases and run the evaluation.</p></div> : (
          <>
            <div className="tablewrap"><table className="tbl only-desktop">
              <thead><tr><th>Skill</th><th>Version</th><th>Cases</th><th title="Latest finished evaluation on this version">Latest evaluation</th><th title="Whether the latest evaluation ran on the current case set and meets release_criteria.min_eval_pass_rate">Evaluation gate</th><th>Approval</th><th>Publishable</th></tr></thead>
              <tbody>{rows.map(({ s, skill }) => { const eg = evalGate(s), ag = approvalGate(s); return (
                <tr key={s.version_id}>
                  <td><Link href={`/skills/${skill.slug}/evaluations?v=${s.version}`} className="cell-name">{skillTitle(skill.name)}</Link></td>
                  <td><span className="muted">v{s.version}</span> <VersionPill status={s.status} small /></td>
                  <td className="num">{s.eval_case_count}</td>
                  <td className="ink-2">{s.latest_eval_run_id ? <>{pct(s.latest_eval_pass_rate)} <span className="caption">{s.eval_current && s.latest_eval_pass_rate != null ? `· ${Math.round(Number(s.latest_eval_pass_rate) * s.eval_case_count)} of ${s.eval_case_count} cases ` : "· on an older case set "}· <LocalTime iso={s.latest_eval_at} /></span></> : <span className="muted">not run</span>}</td>
                  <td><span className={eg.met ? "pass" : "fail"}>{eg.met ? "met" : "not met"}</span> <span className="caption">{eg.tone === "none" ? "(no gate)" : `(≥ ${pct(s.min_eval_pass_rate)})`}</span></td>
                  <td><span className={ag.met ? "pass" : "fail"}>{ag.met ? (s.require_approval ? "valid" : "not required") : s.approval_stale ? "stale" : s.status === "in_review" ? "pending" : "none"}</span></td>
                  <td>{s.status === "published" ? <span className="muted">published</span> : s.publishable ? <span className="pass">yes</span> : <span className="muted">no</span>}</td>
                </tr>); })}</tbody>
            </table></div>
            <div className="row-list only-mobile">{rows.map(({ s, skill }) => { const eg = evalGate(s), ag = approvalGate(s); return (
              <Link key={s.version_id} href={`/skills/${skill.slug}/evaluations?v=${s.version}`} className="row-card">
                <div className="row-card-top"><span className="row-card-name">{skillTitle(skill.name)} <span className="muted">v{s.version}</span></span><VersionPill status={s.status} small /></div>
                <div className="row-card-meta"><span>{s.eval_case_count} cases</span><span>Eval <b>{s.latest_eval_run_id ? pct(s.latest_eval_pass_rate) : "not run"}</b></span><span>Gate <b className={eg.met ? "pass" : "fail"}>{eg.met ? "met" : "not met"}</b></span><span>Approval <b className={ag.met ? "pass" : "fail"}>{ag.met ? "ok" : s.approval_stale ? "stale" : "none"}</b></span></div>
              </Link>); })}</div>
          </>
        )}
      </div>
      <section className="section">
        <SectionHead title="Repository" em="evals" caption={`Behavioural eval results shipped with the repository (${modelLabel(meta.model)} · ${meta.runs} runs · ${meta.date}). These measure the repository SKILL.md files, not workspace versions.`} />
        <div className="flex flex-wrap gap-3"><Link href="/evals/" className="btn btn-secondary">Open the scorecard</Link><Link href="/findings/" className="btn btn-secondary">Open the findings</Link></div>
      </section>
    </>
  );
}
