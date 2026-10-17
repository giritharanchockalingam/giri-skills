"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import type { ScoreRow, Verdict, Misroute, FailedItem } from "@/lib/data";
import { skillHref } from "@/lib/data";
import { VerdictBadge, Lift, Trig } from "./Badge";
import { Chips } from "./Chips";

export interface ScorecardDrill { misroutes: Misroute[]; failed: FailedItem[] }

type Key = keyof ScoreRow;
const COLS: { key: Key; label: string; num?: boolean }[] = [
  { key: "name", label: "Skill" },
  { key: "domain", label: "Domain" },
  { key: "verdict", label: "Verdict" },
  { key: "triggerAcc", label: "Trigger", num: true },
  { key: "fpRate", label: "FP rate", num: true },
  { key: "without", label: "Without", num: true },
  { key: "with", label: "With", num: true },
  { key: "lift", label: "Lift", num: true },
];
const VORDER: Record<Verdict, number> = { OK: 0, DESC: 1, BODY: 2, BOTH: 3 };

export function ScorecardTable({ rows, domains, verdicts, drill }: {
  rows: ScoreRow[]; domains: string[]; verdicts: Verdict[]; drill: Record<string, ScorecardDrill>;
}) {
  const [sortKey, setSortKey] = useState<Key>("lift");
  const [asc, setAsc] = useState(true);
  const [dom, setDom] = useState<Set<string>>(new Set());
  const [ver, setVer] = useState<Set<Verdict>>(new Set());
  const [open, setOpen] = useState<Set<string>>(new Set());

  const sorted = useMemo(() => {
    const f = rows.filter((r) => (dom.size === 0 || dom.has(r.domain)) && (ver.size === 0 || ver.has(r.verdict)));
    const cmp = (a: ScoreRow, b: ScoreRow) => {
      const x = a[sortKey], y = b[sortKey];
      let c = 0;
      if (sortKey === "verdict") c = VORDER[a.verdict] - VORDER[b.verdict];
      else if (typeof x === "number" && typeof y === "number") c = x - y;
      else c = String(x).localeCompare(String(y));
      return (c || a.skill.localeCompare(b.skill)) * (asc ? 1 : -1);
    };
    return [...f].sort(cmp);
  }, [rows, dom, ver, sortKey, asc]);

  const onSort = (k: Key) => { if (k === sortKey) setAsc(!asc); else { setSortKey(k); setAsc(true); } };
  const toggle = (id: string) => setOpen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  return (
    <div className="flex flex-col gap-5">
      <div className="card toolbar">
        <Chips label="domain" options={domains} value={dom} onChange={setDom} />
        <Chips label="verdict" options={verdicts} value={ver} onChange={setVer} />
        <span className="toolbar-count">{sorted.length} of {rows.length} · click a row to drill</span>
      </div>
      <div className="card tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 36 }} aria-label="expand"></th>
              {COLS.map((c) => (
                <th key={c.key} className={`sortable ${c.num ? "num" : ""}`} onClick={() => onSort(c.key)} aria-sort={sortKey === c.key ? (asc ? "ascending" : "descending") : "none"}>
                  {c.label}{sortKey === c.key && <span className="sort-ind" aria-hidden="true">{asc ? "▲" : "▼"}</span>}
                </th>
              ))}
              <th className="num">Misrouted</th>
              <th className="num">With-fails</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const d = drill[r.skill] ?? { misroutes: [], failed: [] };
              const isOpen = open.has(r.skill);
              const failTotal = d.failed.reduce((a, f) => a + f.fails, 0);
              return (
                <RowGroup key={r.skill} isOpen={isOpen} onToggle={() => toggle(r.skill)} detail={<td colSpan={11}><Drill d={d} /></td>}>
                  <td><span className={`caret ${isOpen ? "open" : ""}`} aria-hidden="true">▶</span></td>
                  <td><Link href={skillHref(r.skill)} className="cell-name" onClick={(e) => e.stopPropagation()}>{r.name}</Link></td>
                  <td><span className="tag">{r.domain}</span></td>
                  <td><VerdictBadge v={r.verdict} /></td>
                  <td className="num"><Trig n={r.triggerAcc} /></td>
                  <td className={`num ${r.fpRate > 0 ? "num-neg" : ""}`}>{r.fpRate.toFixed(2)}</td>
                  <td className="num">{r.without.toFixed(2)}</td>
                  <td className="num">{r.with.toFixed(2)}</td>
                  <td className="num"><Lift n={r.lift} /></td>
                  <td className="num">{d.misroutes.length || <span className="muted">0</span>}</td>
                  <td className="num">{failTotal || <span className="muted">0</span>}</td>
                </RowGroup>
              );
            })}
            {sorted.length === 0 && <tr><td colSpan={11} className="none">No skills match.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RowGroup({ isOpen, onToggle, children, detail }: { isOpen: boolean; onToggle: () => void; children: React.ReactNode; detail: React.ReactNode }) {
  return (
    <>
      <tr className="clickable" onClick={onToggle} tabIndex={0} aria-expanded={isOpen}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(); } }}>
        {children}
      </tr>
      {isOpen && <tr className="detail">{detail}</tr>}
    </>
  );
}

function Drill({ d }: { d: ScorecardDrill }) {
  return (
    <div className="subpanel grid grid-safe gap-6 lg:grid-cols-2">
      <div>
        <div className="eyebrow mb-2">Misrouted prompts ({d.misroutes.length})</div>
        {d.misroutes.length === 0 ? <div className="none">None — every case routed correctly.</div> : (
          <table className="mini">
            <thead><tr><th>Case</th><th>Run</th><th>Selected</th><th>Prompt</th></tr></thead>
            <tbody>
              {d.misroutes.map((m, i) => (
                <tr key={i}>
                  <td className="mono whitespace-nowrap">{m.caseId}</td>
                  <td className="mono">{m.run}</td>
                  <td className="mono fail whitespace-nowrap">{m.selected}</td>
                  <td className="ink-2">{m.prompt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div>
        <div className="eyebrow mb-2">Most-failed expected items · with-mode (top {d.failed.length})</div>
        {d.failed.length === 0 ? <div className="none">None — all expected items passed with SKILL.md.</div> : (
          <table className="mini">
            <thead><tr><th>Fails</th><th>Case</th><th>Expected · evidence</th></tr></thead>
            <tbody>
              {d.failed.map((f, i) => (
                <tr key={i}>
                  <td className="mono fail whitespace-nowrap">{f.fails}/{f.total}</td>
                  <td className="mono whitespace-nowrap">{f.caseId} <span className="muted">[{f.expectedIdx}]</span></td>
                  <td>
                    <div>{f.expected}</div>
                    <div className="mt-1 text-[12.5px] text-ink-3">{f.evidence}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
