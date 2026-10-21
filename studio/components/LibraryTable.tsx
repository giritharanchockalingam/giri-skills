"use client";
/* The Library for an employee: plain titles, what each skill gives you, whether it is approved for use here, and its
 * evaluation in words. Approved first. Scores (trigger, lift, cases) live on each skill's page. */
import Link from "next/link";
import { useMemo, useState } from "react";
import { matches } from "@/lib/search";
import { matchesLibraryFilter, type LibraryFilter, type LibraryRow } from "@/lib/library";

const TONE = { proven: "sage", improving: "hold", untested: "none" } as const;
const FILTERS: [LibraryFilter, string][] = [["all", "All"], ["approved", "Approved for use"], ["proven", "Proven"]];

export function LibraryTable({ rows, stages, workspace }: { rows: LibraryRow[]; stages: string[]; workspace: string }) {
  const [q, setQ] = useState("");
  const [show, setShow] = useState<LibraryFilter>("all");
  const [stage, setStage] = useState("all");
  const list = useMemo(() => {
    const n = q.trim().toLowerCase();
    return rows.filter((r) => matchesLibraryFilter(show, r) && (stage === "all" || r.stage === stage) && matches(n, r.title, r.outcome));
  }, [rows, q, show, stage]);
  const Approved = ({ r }: { r: LibraryRow }) => r.published != null
    ? r.mine === false
      ? <span><span className="pill pill-none pill-sm" title={`Approved in ${workspace}, but not in your job roles`}>Approved · v{r.published}</span> <Link className="link caption" href={`/inbox/request?skill=${encodeURIComponent(r.id)}`}>Request access</Link></span>
      : <span className="pill pill-sage pill-sm" title={`Version ${r.published} passed its tests and was approved in ${workspace}. Usable from Claude, Cursor or any app.`}>Approved · v{r.published}</span>
    : <span className="muted" title={`Not approved in ${workspace} yet. You can still try it on its example.`}>Not yet</span>;
  const Evidence = ({ r }: { r: LibraryRow }) => <span className={`pill pill-${TONE[r.evidence]} pill-sm`} title={r.evidenceNote}>{r.evidenceLabel}</span>;

  return (
    <div className="flex flex-col gap-5">
      <div className="card toolbar">
        <input className="input" type="search" placeholder="What do you need done?" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search skills" />
        <div className="chip-group" role="group" aria-label="Show">
          {FILTERS.map(([k, label]) => <button key={k} type="button" className="chip" aria-pressed={show === k} onClick={() => setShow(k)}>{label}</button>)}
        </div>
        <select className="input" value={stage} onChange={(e) => setStage(e.target.value)} aria-label="Lifecycle stage" style={{ maxWidth: 240 }}>
          <option value="all">All stages</option>
          {stages.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="toolbar-count">{list.length} of {rows.length} skills</span>
        <p className="caption" style={{ flexBasis: "100%", margin: 0 }}><b>Approved for use</b> — tested and signed off in {workspace}; runs from your tools. <b>Proven</b> — its evaluation shows it is picked for the right requests and clearly improves the answer. A skill can be one without the other.</p>
      </div>

      <div className="card">
        <div className="tablewrap"><table className="tbl only-desktop">
          <thead><tr><th>Skill — what you get</th><th>Stage</th><th>Approved in {workspace}</th><th>Evaluation</th></tr></thead>
          <tbody>
            {list.map((r) => (
              <tr key={r.id}>
                <td><Link href={`/library/${r.id}/`} className="cell-name">{r.title}</Link><div className="caption">{r.outcome}</div></td>
                <td className="muted">{r.stage}</td>
                <td><Approved r={r} /></td>
                <td><Evidence r={r} /></td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan={4} className="none">No skills match.</td></tr>}
          </tbody>
        </table></div>
        <div className="row-list only-mobile">
          {list.map((r) => (
            <Link key={r.id} href={`/library/${r.id}/`} className="row-card">
              <div className="row-card-top"><span className="row-card-name">{r.title}</span><Evidence r={r} /></div>
              <div className="row-card-desc">{r.outcome}</div>
              <div className="row-card-meta"><span>{r.stage}</span><Approved r={r} /></div>
            </Link>
          ))}
          {list.length === 0 && <div className="row-card none">No skills match.</div>}
        </div>
      </div>
    </div>
  );
}
