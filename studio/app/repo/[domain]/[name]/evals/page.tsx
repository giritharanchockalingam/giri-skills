import { AGENT_COL_TIP } from "@/lib/verdict";
import { loadRepoSkill, repoSkillParams, type RepoParams } from "@/lib/repoSkill";
import { AgentBadge } from "@/components/Badge";
import { AgentCases } from "@/components/AgentCases";
import { CaseEvals } from "@/components/CaseEvals";
import { SectionHead } from "@/components/PageHead";

export function generateStaticParams() { return repoSkillParams(); }
export const dynamicParams = false;

/** Evals: agent cases (deterministic output checks) and the behavioural eval cases with router picks and judge verdicts. */
export default async function RepoSkillEvals({ params }: { params: RepoParams }) {
  const d = await loadRepoSkill(params);
  const { skill, score: sc, agentCases } = d;
  return (
    <>
      <div className="card card-pad">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="h3">Agent eval cases <span className="muted font-normal">({agentCases.length})</span></div>
          <div className="flex items-center gap-2"><AgentBadge v={sc?.agentVerdict} small />{sc?.agentPass != null && <span className="caption">{Math.round(sc.agentPass * 100)}% of checks</span>}</div>
        </div>
        <p className="caption mt-1">{AGENT_COL_TIP}. Open a case for each check and its evidence.</p>
        <AgentCases cases={agentCases} emptyText="Not wired yet — no agent cases ran for this skill." />
      </div>
      <section className="section" style={{ marginTop: 36 }}>
        <SectionHead title="Eval" em="cases" caption={`${skill.cases.length} cases · ${d.trigger.length} router picks · ${d.quality.length} judge verdicts`} />
        <CaseEvals cases={skill.cases} trigger={d.trigger} quality={d.quality} skillName={skill.name} />
      </section>
    </>
  );
}
