import { humanName, skillTitle } from "@/lib/names";
import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { evalGate, approvalGate, nextAction, pct, STATUS_LABEL } from "@/lib/factory/release";
import { gateOf, type GateInput } from "@/lib/factory/funnel";
import { skillDrift, contractKey } from "@/lib/factory/drift";
import { libraryContract, libraryCasesStale } from "@/lib/factory/libraryContract";
import { currentPin, currentSkillSha } from "@/lib/factory/pins";
import { ActionForm } from "@/components/factory/ActionForm";
import { updateFromLibrary } from "@/app/actions";
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
  const newest = [...d.versions].sort((a, b) => b.version - a.version)[0];
  const casesStale = newest?.status === "draft" && newest.source.kind === "repo"
    ? libraryCasesStale(newest.source.repo_skill, ((await d.ctx.supabase.from("sf_eval_cases").select("name, inputs, checks").eq("version_id", newest.id)).data ?? []) as { name: string; inputs: unknown; checks: unknown }[])
    : false;
  const { data: frozenRows } = await d.ctx.supabase.from("sf_version_snapshots").select("version_id, sha256").in("version_id", d.versions.map((v) => v.id));
  const frozen = new Map(((frozenRows ?? []) as { version_id: string; sha256: string }[]).map((r) => [r.version_id, r.sha256]));
  const drift = skillDrift(d.versions.map((v) => ({ ...v, contract: contractKey(v.manifest as never) })), currentPin, libraryContract(d.versions.find((v) => v.source.kind === "repo")?.source.repo_skill), casesStale, frozen, currentSkillSha);
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
      {(drift === "blocked" || drift === "library_updated") && (
        <div className={`notice ${drift === "blocked" ? "notice-err" : "notice-hold"} mb-4`} role="status">
          {drift === "blocked"
            ? <><b>Live version can&apos;t run:</b> the library changed this skill&apos;s files after v{d.published?.version} was approved, so the portal refuses to run files nobody reviewed. Create a version from the library, evaluate it, then approve and publish it.</>
            : <><b>The library has a newer version of this skill</b> (its files or its inputs, outputs and steps changed). {d.published ? <>v{d.published.version} keeps running as approved; </> : null}update to evaluate and publish what the library offers now. Test cases you added to a draft are kept.</>}
          {can(d.ctx.role, "version.create") && <div className="mt-2"><ActionForm action={updateFromLibrary} submit={drift === "blocked" || !["draft"].includes(d.version.status) ? "Create version from library" : "Update draft from library"} hidden={{ skill_id: d.skill.id }} /></div>}
        </div>)}
      <SkillSubNav slug={slug} />
      {children}
    </>
  );
}
