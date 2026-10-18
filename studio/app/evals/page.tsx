import { scorecard, skills, DOMAINS, domainSummaries, misroutesFor, failedWithItemsFor, agentCasesFor, proposalFor, meta } from "@/lib/data";
import { summarize, summarizeAgent, conclusionSentence, VERDICTS_FOR_LEGEND, verdictInfo, type VerdictFilter } from "@/lib/verdict";
import { ScorecardTable, type ScorecardDrill } from "@/components/ScorecardTable";
import { DomainTable } from "@/components/DomainTable";
import { PageHead, SectionHead } from "@/components/PageHead";

export const metadata = { title: "Evals · giri-skills" };

export default function EvalsPage() {
  const s = summarize(scorecard.map((r) => r.verdict));
  const a = summarizeAgent(scorecard.map((r) => r.agentVerdict));
  const { rows: perDomain, total } = domainSummaries();
  const cases = skills.reduce((a, sk) => a + sk.cases.length, 0);
  const drill: Record<string, ScorecardDrill> = Object.fromEntries(
    scorecard.map((r) => [r.skill, {
      misroutes: misroutesFor(r.skill), failed: failedWithItemsFor(r.skill, 5), agentCases: agentCasesFor(r.skill),
      finding: proposalFor(r.skill)?.number ?? null, cases: skills.find((sk) => sk.id === r.skill)?.cases.length ?? 0,
    }]),
  );

  const cards: { value: number; label: React.ReactNode; filter: VerdictFilter; href: string }[] = [
    { value: s.total, label: "skills evaluated", filter: "all", href: "#scorecard?verdict=all" },
    { value: s.healthy, label: <><span className="tone">healthy</span> — no action needed</>, filter: "OK", href: "#scorecard?verdict=OK" },
    { value: s.needsDesc, label: <>need a <span className="tone">better description</span></>, filter: "needs-desc", href: "#scorecard?verdict=needs-desc" },
    { value: s.needsBody, label: <>need <span className="tone">stronger instructions</span></>, filter: "needs-body", href: "#scorecard?verdict=needs-body" },
    { value: a.works, label: <><span className="tone">run as agents</span> — scripts and checks pass</>, filter: "all", href: "#scorecard?verdict=all&runs=Works" },
  ];

  return (
    <>
      <PageHead
        eyebrow="giri-skills · eval results"
        title="What the evals"
        em="found"
        lead={conclusionSentence(s, a)}
        caption={<>{meta.model} · {meta.runs} runs · {cases} cases · {meta.counts.quality.toLocaleString()} judge verdicts · {meta.counts.agent.toLocaleString()} agent checks · {meta.spend} spend (est.) · {meta.date}</>}
      />

      <div className="summary-grid">
        {cards.map((c) => (
          <a key={c.href} href={c.href} className="card card-link summary" aria-label={`Show ${c.value} skills in the scorecard`}>
            <div className="summary-value">{c.value}</div>
            <div className="summary-label">{c.label}</div>
          </a>
        ))}
      </div>

      <section className="section">
        <SectionHead title="Where the" em="work is" caption="A skill can need both fixes, so the four groups below add up to 40; the two “need” counts above do not." />
        <div className="card card-pad">
          <div className="vbar" role="img" aria-label={VERDICTS_FOR_LEGEND.map((v) => `${verdictInfo(v).label} ${s.counts[v]}`).join(", ")}>
            {VERDICTS_FOR_LEGEND.map((v) => s.counts[v] > 0 && (
              <span key={v} className={`vbar-${v}`} style={{ width: `${(s.counts[v] / s.total) * 100}%` }} title={`${verdictInfo(v).label}: ${s.counts[v]}`} />
            ))}
          </div>
          <div className="vlegend">
            {VERDICTS_FOR_LEGEND.map((v) => (
              <div key={v} className="vlegend-item" title={`${v} — ${verdictInfo(v).explanation}`}>
                <span className={`vswatch swatch-${v}`} aria-hidden="true" />
                <span>{verdictInfo(v).label} <b>{s.counts[v]}</b> <span className="muted">· {Math.round((s.counts[v] / s.total) * 100)}%</span></span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <SectionHead title="By" em="domain" caption="Where the healthy skills are, and where the fixes cluster." />
        <DomainTable rows={perDomain} total={total} />
      </section>

      <section className="section" id="scorecard" style={{ scrollMarginTop: 76 }}>
        <SectionHead title="Scorecard" caption="Every skill, worst first. Select a row for the misrouted prompts, the items the judge failed, and the agent run checks." />
        <ScorecardTable rows={scorecard} domains={DOMAINS} drill={drill} />
      </section>
    </>
  );
}
