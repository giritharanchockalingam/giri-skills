import Link from "next/link";
import { verdictInfo, agentVerdictInfo } from "@/lib/verdict";
import { loadRepoSkill, repoSkillParams, type RepoParams } from "@/lib/repoSkill";
import { VerdictBadge, AgentBadge } from "@/components/Badge";

export function generateStaticParams() { return repoSkillParams(); }
export const dynamicParams = false;

export async function generateMetadata({ params }: { params: RepoParams }) {
  const { domain, name } = await params;
  return { title: `${name} · ${domain} · giri-skills` };
}

/** Overview: what/when, the contract (inputs · outputs) and the evidence. Nothing else — the rest is behind the tabs. */
export default async function RepoSkillOverview({ params }: { params: RepoParams }) {
  const d = await loadRepoSkill(params);
  const { skill, score: sc, proposal, agentCases } = d;
  const a = skill.agent;
  const info = verdictInfo(sc?.verdict), agentInfo = agentVerdictInfo(sc?.agentVerdict);
  // first sentence of the frontmatter description (the full text is in the header, "more" expands it)
  const useWhen = (skill.description.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? skill.description).replace(/^Use when\s+/i, "");
  const agentPassed = agentCases.reduce((n, c) => n + c.passed, 0), agentTotal = agentCases.reduce((n, c) => n + c.total, 0);
  return (
    <div className="detail-grid">
      <div className="stack min-w-0">
        <div className="card card-pad">
          <div className="h3">What it does · when to use it</div>
          <dl className="kv mt-3">
            <dt>Use when</dt><dd>{useWhen}</dd>
            <dt>Runs</dt><dd>{a ? <>{a.steps.length} step{a.steps.length === 1 ? "" : "s"} ({a.steps.map((s) => s.kind).join(", ")}) via <code>run_skill.py</code></> : <span className="none">as instructions only — no <code>metadata.agent</code> block</span>}</dd>
            <dt>Domain</dt><dd>{skill.domain}{skill.metadata.version && <> · v{skill.metadata.version}</>}</dd>
          </dl>
        </div>
        <div className="card card-pad">
          <div className="h3">Inputs <span className="muted font-normal">({a?.inputs.length ?? 0})</span></div>
          {!a || a.inputs.length === 0 ? <p className="none mt-2">{a ? "No inputs." : "Not wired — nothing to supply."}</p> : (
            <div className="tablewrap"><table className="mini agent-inputs mt-2">
              <thead><tr><th>Name</th><th>Required</th><th>Type</th></tr></thead>
              <tbody>{a.inputs.map((i) => (
                <tr key={i.name}><td><code>{i.name}</code></td><td>{i.required ? <span className="agent-req">yes</span> : <span className="muted">no</span>}</td><td className="muted">{i.type || "—"}</td></tr>
              ))}</tbody>
            </table></div>
          )}
          <div className="h3 mt-5">Outputs <span className="muted font-normal">({a?.outputs.length ?? 0})</span></div>
          {!a || a.outputs.length === 0 ? <p className="none mt-2">None declared.</p> : (
            <ul className="agent-list mt-2">{a.outputs.map((o) => <li key={o.path}><code>{o.path}</code>{o.checks.length > 0 && <span className="caption">{o.checks.length} check{o.checks.length === 1 ? "" : "s"}</span>}</li>)}</ul>
          )}
        </div>
      </div>
      <aside className="sidebar">
        <div className="card card-pad">
          <div className="h3 mb-3">Evidence</div>
          <dl className="kv">
            <dt>Eval verdict</dt><dd><VerdictBadge v={sc?.verdict} small /><div className="caption mt-1">{info.explanation}</div></dd>
            <dt>Runs</dt><dd><AgentBadge v={sc?.agentVerdict} small />{agentTotal > 0 && <span className="caption"> {agentPassed} of {agentTotal} checks</span>}<div className="caption mt-1">{agentInfo.explanation}</div></dd>
            <dt>Cases</dt><dd>{skill.cases.length} eval · {agentCases.length} agent — <Link href={`${d.base}/evals/`} className="link">see results</Link></dd>
            {proposal && <><dt>Finding</dt><dd><Link href={`/findings/#${proposal.number}`} className="link-flame">Fix proposal #{proposal.number} →</Link> <span className="caption tnum">{proposal.stats}</span></dd></>}
          </dl>
        </div>
      </aside>
    </div>
  );
}
