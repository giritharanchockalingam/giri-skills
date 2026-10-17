import { scorecard, DOMAINS, VERDICTS, misroutesFor, failedWithItemsFor, meta } from "@/lib/data";
import type { Verdict } from "@/lib/data";
import { ScorecardTable, type ScorecardDrill } from "@/components/ScorecardTable";
import { VerdictBadge } from "@/components/Badge";

export const metadata = { title: "Evals · giri-skills" };

const VCOLOR: Record<Verdict, string> = { OK: "var(--ok)", DESC: "var(--warn)", BODY: "var(--orange)", BOTH: "var(--bad)" };

export default function EvalsPage() {
  const counts = Object.fromEntries(VERDICTS.map((v) => [v, scorecard.filter((r) => r.verdict === v).length])) as Record<Verdict, number>;
  const total = scorecard.length;
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

  return (
    <>
      <h1 className="mb-2">Eval dashboard</h1>
      <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="panel p-3">
          <div className="mb-2 text-[10.5px] uppercase tracking-wide text-fg-3">verdict distribution · {total} skills</div>
          <div className="flex h-4 w-full overflow-hidden rounded" role="img" aria-label={VERDICTS.map((v) => `${v} ${counts[v]}`).join(", ")}>
            {VERDICTS.map((v) => counts[v] > 0 && (
              <div key={v} style={{ width: `${(counts[v] / total) * 100}%`, background: VCOLOR[v] }} title={`${v}: ${counts[v]}`} />
            ))}
          </div>
          <div className="mt-2 grid grid-cols-4 gap-2">
            {VERDICTS.map((v) => (
              <div key={v}>
                <VerdictBadge v={v} />
                <div className="mono text-[18px] leading-tight">{counts[v]}</div>
                <div className="mono text-[11px] text-fg-3">{((counts[v] / total) * 100).toFixed(0)}%</div>
              </div>
            ))}
          </div>
          <div className="mt-3 text-[11px] text-fg-3">
            OK = trigger ≥ 0.8 and lift ≥ +0.2 · DESC = trigger &lt; 0.8 · BODY = lift &lt; 0.2 · BOTH = both
          </div>
        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>domain</th><th className="num">skills</th>
                {VERDICTS.map((v) => <th key={v} className="num">{v}</th>)}
                <th className="num">avg trigger</th><th className="num">avg lift</th>
              </tr>
            </thead>
            <tbody>
              {perDomain.map((d) => (
                <tr key={d.domain}>
                  <td>{d.domain}</td><td className="num">{d.n}</td>
                  {VERDICTS.map((v) => <td key={v} className="num">{d[v] || <span className="muted">0</span>}</td>)}
                  <td className="num">{d.avgTrigger.toFixed(2)}</td>
                  <td className={`num ${d.avgLift < 0 ? "lift-neg" : d.avgLift >= 0.2 ? "lift-pos" : ""}`}>{(d.avgLift > 0 ? "+" : "") + d.avgLift.toFixed(2)}</td>
                </tr>
              ))}
              <tr className="font-semibold">
                <td>total</td><td className="num">{total}</td>
                {VERDICTS.map((v) => <td key={v} className="num">{counts[v]}</td>)}
                <td className="num">{(scorecard.reduce((a, r) => a + r.triggerAcc, 0) / total).toFixed(2)}</td>
                <td className="num">{(() => { const l = scorecard.reduce((a, r) => a + r.lift, 0) / total; return (l > 0 ? "+" : "") + l.toFixed(2); })()}</td>
              </tr>
            </tbody>
          </table>
          <div className="px-2 py-1 text-[11px] text-fg-3">
            {meta.counts.trigger} trigger rows · {meta.counts.quality} quality rows · results {meta.resultsDir}
          </div>
        </div>
      </div>

      <h2>Scorecard</h2>
      <ScorecardTable rows={scorecard} domains={DOMAINS} verdicts={VERDICTS} drill={drill} />
    </>
  );
}
