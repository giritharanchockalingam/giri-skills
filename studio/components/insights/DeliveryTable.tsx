import Link from "next/link";
import type { DeliveryRow } from "@/lib/db/delivery";
import { BAND_LABEL, fmtHours, type Band, type Delivery } from "@/lib/insights/delivery";

const BAND_CLS: Record<Band, string> = { elite: "pill-sage", high: "pill-sage", medium: "pill-hold", low: "pill-rust" };
const BandPill = ({ b }: { b: Band | null }) => (b ? <span className={`pill pill-sm ${BAND_CLS[b]}`}>{BAND_LABEL[b]}</span> : <span className="caption">—</span>);

/** Delivery metrics per repository for one window (30 or 90 days), with what each number measures. */
export function DeliveryTable({ rows, window }: { rows: DeliveryRow[]; window: 30 | 90 }) {
  const pick = (r: DeliveryRow): Delivery => (window === 90 ? r.d90 : r.d30);
  return (
    <div className="tablewrap"><table className="mini cat-table">
      <thead><tr><th>Repository</th><th title="Production deployments GitHub recorded, else merges to the default branch">Deploys / week</th><th title="Pull request opened → merged (median; p75)">Lead time</th><th title="Merges that revert or hotfix a change">Change failure</th><th>Open PRs</th><th>Measured</th></tr></thead>
      <tbody>{rows.map((r) => { const d = pick(r); return (
        <tr key={r.entity_id}>
          <td><Link className="link" href={`/catalog/${r.entity_id}`}>{r.key}</Link></td>
          <td>{d.deploys.per_week} <BandPill b={d.deploys.band} /><div className="caption">{d.deploys.count} {d.deploys.source === "deployments" ? "production deployments" : "merges"} in {d.window_days} days</div></td>
          <td>{fmtHours(d.lead_time.median_hours)} <BandPill b={d.lead_time.band} /><div className="caption">p75 {fmtHours(d.lead_time.p75_hours)} · {d.lead_time.samples} PR{d.lead_time.samples === 1 ? "" : "s"}</div></td>
          <td>{d.change_failure.rate == null ? "—" : `${d.change_failure.rate}%`}<div className="caption" title={d.change_failure.examples.join("\n")}>{d.change_failure.failures} of {d.change_failure.of} merges</div></td>
          <td>{d.open_prs.count}{d.open_prs.oldest_days != null && <div className="caption">oldest {d.open_prs.oldest_days} days</div>}</td>
          <td className="caption">{new Date(r.computed_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}{r.notes.length > 0 && <div title={r.notes.join("\n")}>ⓘ {r.notes.length} note{r.notes.length === 1 ? "" : "s"}</div>}</td>
        </tr>); })}</tbody>
    </table></div>
  );
}
