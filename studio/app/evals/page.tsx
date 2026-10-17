import { scorecard, skills, DOMAINS, VERDICTS, misroutesFor, failedWithItemsFor, meta } from "@/lib/data";
import type { Verdict } from "@/lib/data";
import { ScorecardTable, type ScorecardDrill } from "@/components/ScorecardTable";
import { Lift, VerdictBadge } from "@/components/Badge";
import { PageHead, SectionHead, StatStrip } from "@/components/PageHead";

export const metadata = { title: "Evals · giri-skills" };

export default function EvalsPage() {
  const counts = Object.fromEntries(VERDICTS.map((v) => [v, scorecard.filter((r) => r.verdict === v).length])) as Record<Verdict, number>;
  const total = scorecard.length;
  const avgLift = scorecard.reduce((a, r) => a + r.lift, 0) / total;
  const avgTrig = scorecard.reduce((a, r) => a + r.triggerAcc, 0) / total;
  const perDomain = DOMAINS.map((d) => {
    const rows = scorecard.filter((r) => r.domain === d);
    const avg = (k: "triggerAcc" | "lift") => rows.reduce((a, r) => a + r[k], 0) / (rows.length || 1);
    return {
      domain: d, n: rows.length,
      ...Object.fromEntries(VERDICTS.map((v) => [v, rows.filter((r) => r.verdict === v).length])) as Record<Verdict, number>,
      avgTrigger: avg("triggerAcc"), avgLift: avg("lift"),
    };
  });
  const drill: Record<string, ScorecardDrill> = Object.fromEntries(
    scorecard.map((r) => [r.skill, { misroutes: misroutesFor(r.skill), failed: failedWithItemsFor(r.skill, 5) }]),
  );
  const cases = skills.reduce((a, s) => a + s.cases.length, 0);

  return (
    <>
      <PageHead
        eyebrow="giri-skills · eval dashboard"
        title="What the evals"
        em="found"
        sub={<>{meta.model} · {meta.runs} runs · {cases} cases · {meta.counts.quality.toLocaleString()} judge verdicts · {meta.spend} spend (est.)</>}
      />

      <div className="card card-pad">
        <StatStrip stats={[
          { label: "skills", value: total },
          { label: "OK", value: counts.OK },
          { label: "DESC", value: counts.DESC },
          { label: "BODY", value: counts.BODY },
          { label: "BOTH", value: counts.BOTH },
          { label: "avg lift", value: <Lift n={avgLift} /> },
        ]} />
      </div>

      <div className="mt-6 grid grid-safe gap-6 lg:grid-cols-[380px_minmax(0,1fr)] lg:items-start">
        <div className="card card-pad">
          <div className="eyebrow">Verdict distribution · {total} skills</div>
          <div className="vbar mt-4" role="img" aria-label={VERDICTS.map((v) => `${v} ${counts[v]}`).join(", ")}>
            {VERDICTS.map((v) => counts[v] > 0 && (
              <span key={v} className={`vbar-${v}`} style={{ width: `${(counts[v] / total) * 100}%` }} title={`${v}: ${counts[v]}`} />
            ))}
          </div>
          <div className="vlegend">
            {VERDICTS.map((v) => (
              <div key={v}>
                <span className={`vswatch vbar-${v}`} aria-hidden="true" /><span className="tag">{v}</span>
                <div className="v-count">{counts[v]}</div>
                <div className="v-pct">{((counts[v] / total) * 100).toFixed(0)}%</div>
              </div>
            ))}
          </div>
          <p className="mt-5 text-[13px] leading-relaxed text-ink-3">
            <VerdictBadge v="OK" /> trigger ≥ 0.8 and lift ≥ +0.2 · <VerdictBadge v="DESC" /> trigger &lt; 0.8 · <VerdictBadge v="BODY" /> lift &lt; +0.2 · <VerdictBadge v="BOTH" /> both
          </p>
        </div>

        <div className="card">
          <div className="card-head"><span className="card-title">Per domain</span><span className="tag">{meta.counts.trigger} trigger rows · {meta.counts.quality} quality rows</span></div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Domain</th><th className="num">Skills</th>
                  {VERDICTS.map((v) => <th key={v} className="num">{v}</th>)}
                  <th className="num">Avg trigger</th><th className="num">Avg lift</th>
                </tr>
              </thead>
              <tbody>
                {perDomain.map((d) => (
                  <tr key={d.domain}>
                    <td className="cell-name">{d.domain}</td><td className="num">{d.n}</td>
                    {VERDICTS.map((v) => <td key={v} className="num">{d[v] || <span className="muted">0</span>}</td>)}
                    <td className="num">{d.avgTrigger.toFixed(2)}</td>
                    <td className="num"><Lift n={d.avgLift} /></td>
                  </tr>
                ))}
                <tr className="total">
                  <td>Total</td><td className="num">{total}</td>
                  {VERDICTS.map((v) => <td key={v} className="num">{counts[v]}</td>)}
                  <td className="num">{avgTrig.toFixed(2)}</td>
                  <td className="num"><Lift n={avgLift} /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <section className="section">
        <SectionHead eyebrow="Per skill" title="Scorecard" right={<span className="tag">results {meta.resultsDir}</span>} />
        <ScorecardTable rows={scorecard} domains={DOMAINS} verdicts={VERDICTS} drill={drill} />
      </section>
    </>
  );
}
