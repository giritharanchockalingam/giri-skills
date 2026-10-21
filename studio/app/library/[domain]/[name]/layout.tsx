import { humanName } from "@/lib/names";
import { displayDescription } from "@/lib/names";
import Link from "next/link";
import { fmt } from "@/lib/data";
import { verdictInfo } from "@/lib/verdict";
import { loadRepoSkill, repoSkillParams, REPO_TABS, type RepoParams } from "@/lib/repoSkill";
import { VerdictBadge, AgentBadge, Lift, Trig } from "@/components/Badge";
import { COL_TIPS } from "@/components/DomainTable";
import { DetailHead } from "@/components/DetailHead";
import { TabBar } from "@/components/TabBar";

export function generateStaticParams() { return repoSkillParams(); }
export const dynamicParams = false;

export async function generateMetadata({ params }: { params: Promise<{ domain: string; name: string }> }) { const { name } = await params; return { title: `${humanName(name)} · Library · Skills Factory` }; }

/** Repository skill: one-screen header (name, verdicts, description, scorecard strip, Test skill) + the tab bar.
 *  Each tab is a sub-route; only the active tab's content renders. */
export default async function RepoSkillLayout({ children, params }: { children: React.ReactNode; params: RepoParams }) {
  const d = await loadRepoSkill(params);
  const { skill, score: sc } = d;
  const fileCount = skill.files.references.length + skill.files.assets.length + skill.files.scripts.length;
  const tabs = REPO_TABS.map((t) => ({ ...t, count: t.seg === "evals" ? skill.cases.length + d.agentCases.length : t.seg === "files" ? fileCount : undefined }));
  return (
    <>
      <DetailHead
        crumbs={<><Link href="/library/" className="link">Library</Link> <span aria-hidden="true">›</span> {d.domain}</>}
        title={humanName(skill.name)}
        pills={<><VerdictBadge v={sc?.verdict} small /><AgentBadge v={sc?.agentVerdict} small /></>}
        description={displayDescription(skill.description)}
        meta={<>{skill.name}{skill.metadata.version && <> · v{skill.metadata.version}</>}{skill.metadata.author && <> · {skill.metadata.author}</>}{skill.license && <> · {skill.license}</>} · <span title={verdictInfo(sc?.verdict).explanation}>{verdictInfo(sc?.verdict).label}</span></>}
        stats={[
          { label: "Trigger", value: <Trig n={sc?.triggerAcc} />, title: COL_TIPS.trigger },
          { label: "FP rate", value: fmt(sc?.fpRate), title: COL_TIPS.fp },
          { label: "Without", value: fmt(sc?.without), title: COL_TIPS.without },
          { label: "With", value: fmt(sc?.with), title: COL_TIPS.with },
          { label: "Lift", value: <Lift n={sc?.lift} />, title: COL_TIPS.lift },
          { label: "End-to-end checks", value: sc?.agentPass != null ? `${Math.round(sc.agentPass * 100)}%` : "—", title: "Share of end-to-end output checks passed (the skill run for real on its test inputs)" },
        ]}
        primary={skill.agent ? <Link href={`${d.base}/test/`} className="btn btn-primary">Test skill</Link> : <Link href={`${d.base}/instructions/`} className="btn btn-secondary">Read instructions</Link>}
      />
      <p className="caption metric-defs-line"><b>Trigger</b> — when someone asks for this job, does the right skill get picked? · <b>Lift</b> — do the skill&apos;s instructions actually make the answer better than the model would do alone? · <b>FP rate</b> — how often it was picked for a request it should not handle. · <b>Without / With</b> — share of expected items the answer got right without and with the skill.</p>
      <TabBar base={d.base} tabs={tabs} keep={[]} label="Skill views" />
      {children}
    </>
  );
}
