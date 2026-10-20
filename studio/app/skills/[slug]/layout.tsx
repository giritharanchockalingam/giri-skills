import { humanName, skillTitle } from "@/lib/names";
import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { evalGate, approvalGate, nextAction, pct, STATUS_LABEL } from "@/lib/factory/release";
import { gateOf, type GateInput } from "@/lib/factory/funnel";
import { can } from "@/lib/factory/roles";
import { SkillPill, GatePill } from "@/components/factory/Pills";
import { SkillSubNav } from "@/components/factory/SkillSubNav";
import { DetailHead } from "@/components/DetailHead";

export const dynamic = "force-dynamic";
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) { const { slug } = await params; return { title: `${humanName(slug)} · Publish pipeline · Skills Factory` }; }

/** Factory skill: one-screen header (name · status · purpose · owner/version · stat strip · next action) + the tab bar.
 *  Layouts cannot read ?v=, so the header describes the latest version; each tab shows the version it was given. */
export default async function SkillLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const d = await loadSkillPage(slug, null);
  const s = d.state;
  const na = s ? nextAction(s, d.runCount > 0) : null;
  const vq = `?v=${d.version.version}`;
  const href = (a: string) => a === "edit" ? `/skills/${slug}/authoring/${vq}` : a === "test" ? `/skills/${slug}/test/${vq}` : a === "add_cases" || a === "run_eval" ? `/skills/${slug}/evaluations/${vq}` : `/skills/${slug}/release/${vq}`;
  const allowed = !na ? false : na.who === "reviewer" ? can(d.ctx.role, "version.review") : na.action === "new_draft" ? can(d.ctx.role, "version.create") : na.action === "publish" ? can(d.ctx.role, "version.publish") : can(d.ctx.role, "version.edit");
  // the header's one status is the funnel stage — the same words the pipeline and Home count with
  const working = ["draft", "in_review", "approved"].includes(d.version.status) ? (s as GateInput | null) : null;
  const gate = d.skill.status === "retired" ? null : gateOf(working, !!d.published);
  const eg = s ? evalGate(s) : null, ag = s ? approvalGate(s) : null;
  return (
    <>
      <DetailHead
        crumbs={<><Link href="/pipeline" className="link">Publish pipeline</Link> <span aria-hidden="true">›</span> {skillTitle(d.skill.name)}</>}
        title={skillTitle(d.skill.name)}
        pills={<>{gate ? <GatePill gate={gate} small /> : <SkillPill status={d.skill.status} small />}{d.published && gate !== "published" && <span className="caption">v{d.published.version} is live</span>}</>}
        description={d.skill.purpose || "No purpose written yet — add one under Instructions."}
        meta={<>{d.published ? <>Published <b>v{d.published.version}</b></> : "Not published yet"} · {d.versions.length} version{d.versions.length === 1 ? "" : "s"} · latest v{d.version.version} · owner {d.skill.owner_id === d.ctx.user.id ? "you" : d.skill.owner_id.slice(0, 8)}</>}
        stats={[
          { label: "Latest version", value: `v${d.version.version}`, title: `Version record status: ${STATUS_LABEL[d.version.status]}` },
          { label: "Eval pass rate", value: s?.latest_eval_run_id ? pct(s.latest_eval_pass_rate) : "—", title: s?.latest_eval_run_id ? `Latest evaluation on ${s.eval_case_count} case(s)` : "No evaluation has run on the latest version" },
          { label: "Eval cases", value: s?.eval_case_count ?? 0 },
          { label: "Runs", value: d.runCount, title: "Runs of the latest version" },
          { label: "Eval gate", value: eg ? <span className={eg.met ? "pass" : "fail"}>{eg.met ? "met" : "not met"}</span> : "—", title: eg?.detail },
          { label: "Approval", value: ag ? <span className={ag.met ? "pass" : "fail"}>{ag.met ? "met" : "not met"}</span> : "—", title: ag?.detail },
        ]}
        primary={na && (allowed ? <Link href={href(na.action)} className="btn btn-primary">{na.label}</Link> : <span className="caption">Next: {na.label} ({na.who})</span>)}
        secondary={na?.action !== "test" && na?.action !== "review" && na?.action !== "publish" && !["retired", "superseded"].includes(d.version.status) ? <Link href={`/skills/${slug}/test/${vq}`} className="btn btn-secondary">Test</Link> : null}
      />
      <SkillSubNav slug={slug} />
      {children}
    </>
  );
}
