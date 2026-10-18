import type { DomainSummary } from "@/lib/data";
import { VERDICTS_FOR_LEGEND, verdictInfo, AGENT_COL_TIP } from "@/lib/verdict";
import { Lift, Trig } from "./Badge";

export const COL_TIPS = {
  trigger: "How often the router picked this skill for its own prompts",
  fp: "How often it was picked for unrelated prompts",
  without: "Share of expected items passed without the skill loaded",
  with: "Share of expected items passed with the skill loaded",
  lift: "With minus without",
} as const;

/** Full-width per-domain table on desktop; one stacked block per domain on mobile. */
export function DomainTable({ rows, total, showAverages = true }: { rows: DomainSummary[]; total: DomainSummary; showAverages?: boolean }) {
  const all = [...rows, total];
  return (
    <div className="card">
      <table className="tbl only-desktop">
        <thead>
          <tr>
            <th>Domain</th>
            <th className="num">Skills</th>
            <th className="num">Need work</th>
            {VERDICTS_FOR_LEGEND.map((v) => <th key={v} className="num" title={`${v} — ${verdictInfo(v).explanation}`}>{verdictInfo(v).label}</th>)}
            <th className="num" title={AGENT_COL_TIP}>Runs</th>
            {showAverages && <th className="num" title={COL_TIPS.trigger}>Avg trigger</th>}
            {showAverages && <th className="num" title={COL_TIPS.lift}>Avg lift</th>}
          </tr>
        </thead>
        <tbody>
          {all.map((d, i) => {
            const isTotal = i === all.length - 1;
            return (
              <tr key={d.domain} className={isTotal ? "total" : ""}>
                <td className={isTotal ? "" : "cell-name"}>{d.domain}</td>
                <td className="num">{d.n}</td>
                <td className="num">{d.needsWork}</td>
                {VERDICTS_FOR_LEGEND.map((v) => <td key={v} className="num">{d.counts[v] || <span className="muted">0</span>}</td>)}
                <td className="num">{d.runs || <span className="muted">0</span>}</td>
                {showAverages && <td className="num"><Trig n={d.avgTrigger} /></td>}
                {showAverages && <td className="num"><Lift n={d.avgLift} /></td>}
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="row-list only-mobile">
        {all.map((d, i) => {
          const isTotal = i === all.length - 1;
          return (
            <div key={d.domain} className="row-card" style={{ cursor: "default" }}>
              <div className="row-card-top">
                <span className="row-card-name">{d.domain}</span>
                <span className="caption tnum">{d.needsWork} of {d.n} need work · {d.runs} run as agents</span>
              </div>
              <div className="row-card-meta">
                {VERDICTS_FOR_LEGEND.map((v) => (
                  <span key={v}><span className={`vswatch swatch-${v}`} aria-hidden="true" style={{ marginRight: 6, verticalAlign: -1 }} />{verdictInfo(v).label} <b>{d.counts[v]}</b></span>
                ))}
              </div>
              {showAverages && (
                <div className="row-card-meta">
                  <span>Avg trigger <b><Trig n={d.avgTrigger} /></b></span>
                  <span>Avg lift <b><Lift n={d.avgLift} /></b></span>
                </div>
              )}
              {isTotal && <span className="sr-only">Total</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
