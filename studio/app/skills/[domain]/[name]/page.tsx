import Link from "next/link";
import { notFound } from "next/navigation";
import { skills, scoreFor, proposalFor, trigger, quality, agentCasesFor, fmt } from "@/lib/data";
import { verdictInfo, agentVerdictInfo, AGENT_COL_TIP } from "@/lib/verdict";
import { VerdictBadge, AgentBadge, Lift, Trig } from "@/components/Badge";
import { CaseEvals } from "@/components/CaseEvals";
import { AgentCases } from "@/components/AgentCases";
import { RunPanel } from "@/components/RunPanel";
import { CopyButton } from "@/components/CopyButton";
import { COL_TIPS } from "@/components/DomainTable";
import { SectionHead, StatStrip } from "@/components/PageHead";

export function generateStaticParams() {
  return skills.map((s) => ({ domain: s.domain, name: s.name }));
}
export const dynamicParams = false;

export async function generateMetadata({ params }: { params: Promise<{ domain: string; name: string }> }) {
  const { domain, name } = await params;
  return { title: `${name} · ${domain} · giri-skills` };
}

export default async function SkillPage({ params }: { params: Promise<{ domain: string; name: string }> }) {
  const { domain, name } = await params;
  const id = `${domain}/${name}`;
  const skill = skills.find((s) => s.id === id);
  if (!skill) notFound();
  const sc = scoreFor(id);
  const prop = proposalFor(id);
  const trig = trigger.filter((t) => t.skill === id);
  const qual = quality.filter((q) => q.skill === id);
  const fileCount = skill.files.references.length + skill.files.assets.length + skill.files.scripts.length;
  const info = verdictInfo(sc?.verdict);
  const agentCases = agentCasesFor(id);
  const agentInfo = agentVerdictInfo(sc?.agentVerdict);
  const demoCmd = `python3 scripts/run_skill.py --demo ${id}`;
  // Required inputs plainly; optional ones in [brackets] (usage syntax) so the pasted command stays valid.
  const inputCmd = skill.agent
    ? [`python3 scripts/run_skill.py ${id}`, ...skill.agent.inputs.map((i) => `  ${i.required ? "" : "["}--input ${i.name}=<${i.type || "value"}>${i.required ? "" : "]"}`), "  --out runs/" + name].join(" \\\n")
    : "";

  return (
    <>
      <div className="page-head">
        <nav className="caption" aria-label="Breadcrumb">
          <Link href="/" className="link">Skills</Link> <span aria-hidden="true">›</span> {domain}
        </nav>
        <div className="eyebrow mt-5">{skill.name}{skill.metadata.version && <> · v{skill.metadata.version}</>}</div>
        <h1 className="h1" style={{ marginBottom: 12 }}>{skill.name.replace(/-/g, " ")}</h1>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <VerdictBadge v={sc?.verdict} />
          <span className="caption">{info.explanation}</span>
        </div>
        <p className="lead mt-5">{skill.description}</p>
      </div>

      <div className="card card-pad">
        <StatStrip stats={[
          { label: "Trigger", value: <Trig n={sc?.triggerAcc} />, title: COL_TIPS.trigger },
          { label: "FP rate", value: fmt(sc?.fpRate), title: COL_TIPS.fp },
          { label: "Without", value: fmt(sc?.without), title: COL_TIPS.without },
          { label: "With", value: fmt(sc?.with), title: COL_TIPS.with },
          { label: "Lift", value: <Lift n={sc?.lift} />, title: COL_TIPS.lift },
          { label: "Eval cases", value: skill.cases.length },
        ]} />
      </div>

      <div className="two-col mt-7">
        <div className="flex flex-col gap-5 min-w-0">
        <div className="card card-pad" id="agent">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 mb-2">
            <div className="h3">Runs as an agent</div>
            <div className="flex items-center gap-2"><AgentBadge v={sc?.agentVerdict} /><span className="caption">{sc?.agentPass != null && <>{Math.round(sc.agentPass * 100)}% of checks</>}</span></div>
          </div>
          <p className="caption">{agentInfo.explanation}</p>
          {!skill.agent ? (
            <p className="none mt-4">Not wired yet — this SKILL.md has no <code>metadata.agent</code> block, so <code>run_skill.py</code> cannot run it.</p>
          ) : (
            <>
              <div className="h3 mt-5 mb-2" style={{ fontSize: 14 }}>How to run</div>
              <p className="caption mb-2">On its own happy-path fixtures, from the repo root:</p>
              <div className="codeblock"><CopyButton text={demoCmd} />{demoCmd}</div>
              <p className="caption mt-3 mb-2">With your own inputs (declared below; bracketed ones are optional):</p>
              <div className="codeblock"><CopyButton text={inputCmd} />{inputCmd}</div>

              <div className="h3 mt-6 mb-2" style={{ fontSize: 14 }}>Inputs <span className="muted font-normal">({skill.agent.inputs.length})</span></div>
              <table className="mini agent-inputs">
                <thead><tr><th>Name</th><th>Required</th><th>Type</th><th>From</th></tr></thead>
                <tbody>
                  {skill.agent.inputs.map((i) => (
                    <tr key={i.name}>
                      <td><code>{i.name}</code></td>
                      <td>{i.required ? <span className="agent-req">yes</span> : <span className="muted">no</span>}</td>
                      <td className="muted">{i.type || "—"}</td>
                      <td className="ink-2">{i.from || (i.default != null ? <>default <code>{i.default}</code></> : <span className="muted">—</span>)}{i.from && i.default != null && <> · default <code>{i.default}</code></>}</td>
                    </tr>
                  ))}
                  {skill.agent.inputs.length === 0 && <tr><td colSpan={4} className="none">No inputs.</td></tr>}
                </tbody>
              </table>

              <div className="agent-cols mt-6">
                <div>
                  <div className="h3 mb-2" style={{ fontSize: 14 }}>Steps <span className="muted font-normal">({skill.agent.steps.length})</span></div>
                  <ol className="agent-list">
                    {skill.agent.steps.map((st, k) => (
                      <li key={k}><span className={`agent-kind agent-kind-${st.kind}`}>{st.kind}</span><code>{st.step}</code></li>
                    ))}
                  </ol>
                </div>
                <div className="min-w-0">
                  <div className="h3 mb-2" style={{ fontSize: 14 }}>Outputs <span className="muted font-normal">({skill.agent.outputs.length})</span></div>
                  <ul className="agent-list">
                    {skill.agent.outputs.map((o, k) => (
                      <li key={k}><div className="min-w-0"><code>{o.path}</code>{o.checks.length > 0 && <div className="caption" style={{ overflowWrap: "anywhere" }}>checks: {o.checks.join(", ")}</div>}</div></li>
                    ))}
                  </ul>
                </div>
              </div>
            </>
          )}

          <div className="h3 mt-6 mb-1" style={{ fontSize: 14 }}>Agent eval cases <span className="muted font-normal">({agentCases.length})</span></div>
          <p className="caption">{AGENT_COL_TIP}. Open a case for each check and its evidence.</p>
          <AgentCases cases={agentCases} emptyText="Not wired yet — no agent cases ran for this skill." />
        </div>

        {skill.agent && <RunPanel skillId={id} agent={skill.agent} />}

        <div className="card card-pad">
          <div className="eyebrow mb-4">SKILL.md</div>
          <div className="prose" dangerouslySetInnerHTML={{ __html: skill.bodyHtml }} />
        </div>
        </div>
        <aside className="sidebar">
          {prop && (
            <Link href={`/findings/#${prop.number}`} className="card card-link card-pad block">
              <div className="eyebrow mb-2">Finding</div>
              <div className="serif text-[22px] leading-tight">Fix proposal #{prop.number} <span className="text-flame">→</span></div>
              <div className="caption tnum mt-2">{prop.stats}</div>
            </Link>
          )}
          <div className="card card-pad">
            <div className="h3 mb-3">Files <span className="muted font-normal">({fileCount})</span></div>
            {(["references", "assets", "scripts"] as const).map((k) => (
              <div key={k} className="mb-4 last:mb-0">
                <div className="caption capitalize">{k} ({skill.files[k].length})</div>
                {skill.files[k].length === 0 ? (
                  <div className="none text-[14px]">none</div>
                ) : (
                  <ul className="file-list mt-1">{skill.files[k].map((f) => <li key={f}>{k}/{f}</li>)}</ul>
                )}
              </div>
            ))}
          </div>
          {skill.license && <div className="caption px-1">License · {skill.license}</div>}
        </aside>
      </div>

      <section className="section">
        <SectionHead title="Eval" em="cases" caption={`${skill.cases.length} cases · ${trig.length} router picks · ${qual.length} judge verdicts`} />
        <CaseEvals cases={skill.cases} trigger={trig} quality={qual} skillName={skill.name} />
      </section>
    </>
  );
}
