"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import type { ScoreRow, Verdict, Misroute, FailedItem } from "@/lib/data";
import { skillHref } from "@/lib/data";
import { VerdictBadge, Lift } from "./Badge";
import { Chips } from "./Chips";

export interface ScorecardDrill { misroutes: Misroute[]; failed: FailedItem[] }

type Key = keyof ScoreRow;
const COLS: { key: Key; label: string; num?: boolean }[] = [
  { key: "name", label: "skill" },
  { key: "domain", label: "domain" },
  { key: "verdict", label: "verdict" },
  { key: "triggerAcc", label: "trigger acc", num: true },
  { key: "fpRate", label: "FP rate", num: true },
  { key: "without", label: "without", num: true },
  { key: "with", label: "with", num: true },
  { key: "lift", label: "lift", num: true },
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
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Chips label="domain" options={domains} value={dom} onChange={setDom} />
        <Chips label="verdict" options={verdicts} value={ver} onChange={setVer} />
        <span className="mono ml-auto text-[11.5px] text-fg-3">{sorted.length} of {rows.length} · sort {sortKey} {asc ? "↑" : "↓"} · click a row to drill</span>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th className="w-6"></th>
              {COLS.map((c) => (
                <th key={c.key} className={`sortable ${c.num ? "num" : ""}`} onClick={() => onSort(c.key)} aria-sort={sortKey === c.key ? (asc ? "ascending" : "descending") : "none"}>
                  {c.label}{sortKey === c.key ? (asc ? " ↑" : " ↓") : ""}
                </th>
              ))}
              <th className="num">misrouted</th>
              <th className="num">with-fails</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const d = drill[r.skill] ?? { misroutes: [], failed: [] };
              const isOpen = open.has(r.skill);
              const failTotal = d.failed.reduce((a, f) => a + f.fails, 0);
              return (
                <RowGroup key={r.skill} isOpen={isOpen} onToggle={() => toggle(r.skill)} detail={<td colSpan={11}><Drill d={d} /></td>}>
                  <td className="muted">{isOpen ? "▾" : "▸"}</td>
                  <td className="mono"><Link href={skillHref(r.skill)} onClick={(e) => e.stopPropagation()}>{r.name}</Link></td>
                  <td className="text-fg-2">{r.domain}</td>
                  <td><VerdictBadge v={r.verdict} /></td>
                  <td className={`num ${r.triggerAcc < 0.8 ? "lift-neg" : ""}`}>{r.triggerAcc.toFixed(2)}</td>
                  <td className={`num ${r.fpRate > 0 ? "lift-neg" : ""}`}>{r.fpRate.toFixed(2)}</td>
                  <td className="num">{r.without.toFixed(2)}</td>
                  <td className="num">{r.with.toFixed(2)}</td>
                  <td className="num"><Lift n={r.lift} /></td>
                  <td className="num">{d.misroutes.length || <span className="muted">0</span>}</td>
                  <td className="num">{failTotal || <span className="muted">0</span>}</td>
                </RowGroup>
              );
            })}
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
    <div className="grid gap-3 py-1 lg:grid-cols-2">
      <div>
        <div className="mb-1 text-[10.5px] uppercase tracking-wide text-fg-3">misrouted prompts ({d.misroutes.length})</div>
        {d.misroutes.length === 0 ? <div className="muted text-[12px]">none — every case routed correctly</div> : (
          <table className="w-full text-[12px]">
            <thead><tr className="text-fg-3"><th className="pr-2 text-left font-medium">case</th><th className="pr-2 text-left font-medium">run</th><th className="pr-2 text-left font-medium">selected</th><th className="text-left font-medium">prompt</th></tr></thead>
            <tbody>
              {d.misroutes.map((m, i) => (
                <tr key={i} className="align-top">
                  <td className="mono whitespace-nowrap pr-2 py-0.5">{m.caseId}</td>
                  <td className="mono pr-2 py-0.5">{m.run}</td>
                  <td className="mono fail whitespace-nowrap pr-2 py-0.5">{m.selected}</td>
                  <td className="py-0.5 whitespace-normal text-fg-2">{m.prompt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div>
        <div className="mb-1 text-[10.5px] uppercase tracking-wide text-fg-3">most-failed expected items, with-mode (top {d.failed.length})</div>
        {d.failed.length === 0 ? <div className="muted text-[12px]">none — all expected items passed with SKILL.md</div> : (
          <table className="w-full text-[12px]">
            <thead><tr className="text-fg-3"><th className="pr-2 text-left font-medium">fails</th><th className="pr-2 text-left font-medium">case</th><th className="text-left font-medium">expected · evidence</th></tr></thead>
            <tbody>
              {d.failed.map((f, i) => (
                <tr key={i} className="align-top">
                  <td className="mono fail whitespace-nowrap pr-2 py-0.5">{f.fails}/{f.total}</td>
                  <td className="mono whitespace-nowrap pr-2 py-0.5">{f.caseId} <span className="muted">[{f.expectedIdx}]</span></td>
                  <td className="py-0.5 whitespace-normal">
                    <div>{f.expected}</div>
                    <div className="text-fg-3">{f.evidence}</div>
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
