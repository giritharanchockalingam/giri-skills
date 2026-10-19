"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { ScoreRow, Misroute, FailedItem, AgentCase } from "@/lib/data";
import { skillHref, fmt } from "@/lib/data";
import { isVerdictFilter, matchesVerdictFilter, verdictSeverity, isAgentFilter, matchesAgentFilter, agentVerdictSeverity, AGENT_COL_TIP, AGENT_FILTERS, type VerdictFilter, type AgentFilter } from "@/lib/verdict";
import { VerdictBadge, AgentBadge, Lift, Trig } from "./Badge";
import { DomainFilter, VerdictFilterControl, ChoiceFilter } from "./FilterBar";
import { Drawer } from "./Drawer";
import { AgentCases } from "./AgentCases";
import { COL_TIPS } from "./DomainTable";

export interface ScorecardDrill { misroutes: Misroute[]; failed: FailedItem[]; finding: number | null; cases: number; agentCases: AgentCase[] }
const EMPTY_DRILL: ScorecardDrill = { misroutes: [], failed: [], finding: null, cases: 0, agentCases: [] };

type SortKey = "severity" | "name" | "domain" | "agent" | "triggerAcc" | "fpRate" | "without" | "with" | "lift";
const COLS: { key: SortKey; label: string; num?: boolean; wide?: boolean; title?: string }[] = [
  { key: "name", label: "Skill" },
  { key: "domain", label: "Domain" },
  { key: "severity", label: "Verdict" },
  { key: "agent", label: "Runs", title: AGENT_COL_TIP },
  { key: "triggerAcc", label: "Trigger", num: true, title: COL_TIPS.trigger },
  { key: "fpRate", label: "FP rate", num: true, wide: true, title: COL_TIPS.fp },
  { key: "without", label: "Without", num: true, wide: true, title: COL_TIPS.without },
  { key: "with", label: "With", num: true, wide: true, title: COL_TIPS.with },
  { key: "lift", label: "Lift", num: true, title: COL_TIPS.lift },
];

/** Reads `#scorecard?verdict=…&runs=…&domain=…` so summary cards can deep-link a filter. */
const readHash = (): { verdict?: VerdictFilter; runs?: AgentFilter; domain?: string } => {
  if (typeof window === "undefined") return {};
  const h = window.location.hash;
  if (!h.startsWith("#scorecard")) return {};
  const q = new URLSearchParams(h.split("?")[1] ?? "");
  const v = q.get("verdict");
  const r = q.get("runs");
  return { verdict: isVerdictFilter(v) ? v : undefined, runs: isAgentFilter(r) ? r : undefined, domain: q.get("domain") ?? undefined };
};

export function ScorecardTable({ rows, domains, drill }: { rows: ScoreRow[]; domains: string[]; drill: Record<string, ScorecardDrill> }) {
  const [sortKey, setSortKey] = useState<SortKey>("severity");
  const [asc, setAsc] = useState(true);
  const [dom, setDom] = useState<string>("all");
  const [ver, setVer] = useState<VerdictFilter>("all");
  const [runs, setRuns] = useState<AgentFilter>("all");
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    const apply = () => {
      const h = readHash();
      if (!window.location.hash.startsWith("#scorecard")) return;
      setVer(h.verdict ?? "all");
      setRuns(h.runs ?? "all");
      if (h.domain && domains.includes(h.domain)) setDom(h.domain);
      document.getElementById("scorecard")?.scrollIntoView({ block: "start", behavior: "smooth" });
    };
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, [domains]);

  const sorted = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const f = rows.filter((r) => (dom === "all" || r.domain === dom) && matchesVerdictFilter(ver, r.verdict) && matchesAgentFilter(runs, r.agentVerdict) && (!needle || r.name.toLowerCase().includes(needle)));
    const cmp = (a: ScoreRow, b: ScoreRow) => {
      let c = 0;
      if (sortKey === "severity") c = verdictSeverity(a.verdict) - verdictSeverity(b.verdict) || (a.lift ?? -9) - (b.lift ?? -9);
      else if (sortKey === "agent") c = agentVerdictSeverity(a.agentVerdict) - agentVerdictSeverity(b.agentVerdict) || (a.agentPass ?? 0) - (b.agentPass ?? 0);
      else if (sortKey === "name" || sortKey === "domain") c = a[sortKey].localeCompare(b[sortKey]);
      else c = (a[sortKey] ?? -9) - (b[sortKey] ?? -9);  // not-yet-evaluated rows sort last
      return (c || a.skill.localeCompare(b.skill)) * (asc ? 1 : -1);
    };
    return [...f].sort(cmp);
  }, [rows, dom, ver, runs, q, sortKey, asc]);

  const onSort = (k: SortKey) => { if (k === sortKey) setAsc(!asc); else { setSortKey(k); setAsc(true); } };
  const close = useCallback(() => setOpenId(null), []);
  const openRow = sorted.find((r) => r.skill === openId) ?? rows.find((r) => r.skill === openId) ?? null;

  return (
    <div className="flex flex-col gap-5">
      <div className="card toolbar">
        <input className="input" type="search" placeholder="Search skills" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search skills" />
        <DomainFilter id="sc-domain" domains={domains} value={dom} onChange={setDom} />
        <VerdictFilterControl id="sc-verdict" value={ver} onChange={setVer} />
        <ChoiceFilter id="sc-runs" label="Runs" value={runs} onChange={(v) => setRuns(v)} options={AGENT_FILTERS.filter((f) => f.key !== "all")} />
        <span className="toolbar-count">{sorted.length} of {rows.length} skills · worst first</span>
      </div>

      <div className="card">
        <div className="tablewrap"><table className="tbl only-desktop">
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key} title={c.title} className={`sortable ${c.num ? "num" : ""} ${c.wide ? "col-wide" : ""}`} onClick={() => onSort(c.key)}
                  aria-sort={sortKey === c.key ? (asc ? "ascending" : "descending") : "none"}>
                  {c.label}{sortKey === c.key && <span className="sort-ind" aria-hidden="true">{asc ? "▲" : "▼"}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.skill} className="clickable" onClick={() => setOpenId(r.skill)} tabIndex={0} aria-haspopup="dialog"
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpenId(r.skill); } }}>
                <td><span className="cell-name">{r.name}</span></td>
                <td><span className="domain-tag">{r.domain}</span></td>
                <td><VerdictBadge v={r.verdict} /></td>
                <td><AgentBadge v={r.agentVerdict} /></td>
                <td className="num"><Trig n={r.triggerAcc} /></td>
                <td className={`num col-wide ${(r.fpRate ?? 0) > 0 ? "num-neg" : ""}`}>{fmt(r.fpRate)}</td>
                <td className="num col-wide">{fmt(r.without)}</td>
                <td className="num col-wide">{fmt(r.with)}</td>
                <td className="num"><Lift n={r.lift} /></td>
              </tr>
            ))}
            {sorted.length === 0 && <tr><td colSpan={COLS.length} className="none">No skills match.</td></tr>}
          </tbody>
        </table></div>

        <div className="row-list only-mobile">
          {sorted.map((r) => (
            <button key={r.skill} type="button" className="row-card" onClick={() => setOpenId(r.skill)} aria-haspopup="dialog">
              <div className="row-card-top">
                <span className="row-card-name">{r.name}</span>
                <VerdictBadge v={r.verdict} small />
              </div>
              <div className="row-card-meta">
                <span>{r.domain}</span>
                <span>Lift <b><Lift n={r.lift} /></b></span>
                <span>Trigger <b><Trig n={r.triggerAcc} /></b></span>
                <span>Runs <AgentBadge v={r.agentVerdict} small /></span>
              </div>
            </button>
          ))}
          {sorted.length === 0 && <div className="row-card none">No skills match.</div>}
        </div>
      </div>

      <Drawer open={!!openRow} onClose={close} titleId="scorecard-drawer-title"
        title={openRow && (
          <>
            <div className="caption">{openRow.domain}</div>
            <div id="scorecard-drawer-title" className="drawer-title mt-1">{openRow.name}</div>
            <div className="mt-3"><VerdictBadge v={openRow.verdict} /></div>
          </>
        )}
        foot={openRow && (
          <>
            <Link href={skillHref(openRow.skill)} className="btn btn-primary">Open skill page</Link>
            {drill[openRow.skill]?.finding != null && (
              <Link href={`/findings/#${drill[openRow.skill].finding}`} className="btn btn-secondary">Finding #{drill[openRow.skill].finding}</Link>
            )}
          </>
        )}>
        {openRow && <DrawerBody r={openRow} d={drill[openRow.skill] ?? EMPTY_DRILL} />}
      </Drawer>
    </div>
  );
}

const groupByCase = (ms: Misroute[]) => {
  const out: { caseId: string; prompt: string; runs: Misroute[] }[] = [];
  for (const m of ms) {
    const g = out.find((x) => x.caseId === m.caseId);
    if (g) g.runs.push(m); else out.push({ caseId: m.caseId, prompt: m.prompt, runs: [m] });
  }
  return out;
};

function DrawerBody({ r, d }: { r: ScoreRow; d: ScorecardDrill }) {
  const stat = (label: string, value: React.ReactNode, title: string) => (
    <div className="drawer-stat" title={title}><div className="v">{value}</div><div className="l">{label}</div></div>
  );
  return (
    <>
      <div className="drawer-stats">
        {stat("Trigger", <Trig n={r.triggerAcc} />, COL_TIPS.trigger)}
        {stat("FP rate", <span className={(r.fpRate ?? 0) > 0 ? "num-neg" : ""}>{fmt(r.fpRate)}</span>, COL_TIPS.fp)}
        {stat("Lift", <Lift n={r.lift} />, COL_TIPS.lift)}
        {stat("Without", fmt(r.without), COL_TIPS.without)}
        {stat("With", fmt(r.with), COL_TIPS.with)}
        {stat("Cases", d.cases, "Eval cases for this skill")}
        {stat("Runs", <AgentBadge v={r.agentVerdict} small />, AGENT_COL_TIP)}
      </div>

      <section>
        <h3 className="h3">Misrouted prompts <span className="muted font-normal">({d.misroutes.length})</span></h3>
        <p className="caption mt-1">Prompts written for this skill where the router picked something else.</p>
        {d.misroutes.length === 0 ? <p className="none mt-3">None — every prompt routed here.</p> : (
          <div className="mt-2">
            {groupByCase(d.misroutes).map((g) => (
              <div key={g.caseId} className="item">
                <div className="item-head"><span>{g.caseId}</span><span>{g.runs.length === 1 ? `run ${g.runs[0].run}` : `${g.runs.length} runs`}</span></div>
                <div className="item-text">{g.prompt}</div>
                {g.runs.map((m) => (
                  <div key={m.run} className="item-sub">Run {m.run} picked <span className="fail">{m.selected}</span></div>
                ))}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 className="h3">Most-failed expected items <span className="muted font-normal">({d.failed.length})</span></h3>
        <p className="caption mt-1">Judged with the skill loaded. Fail count across runs, then one line of evidence.</p>
        {d.failed.length === 0 ? <p className="none mt-3">None — every expected item passed with the skill loaded.</p> : (
          <div className="mt-2">
            {d.failed.map((f, i) => (
              <div key={i} className="item">
                <div className="item-head"><span>{f.caseId} · item {f.expectedIdx + 1}</span><span className="fail">{f.fails} of {f.total} failed</span></div>
                <div className="item-text">{f.expected}</div>
                {f.evidence && <div className="item-sub">{f.evidence}</div>}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 className="h3">Agent run <span className="muted font-normal">({d.agentCases.length} {d.agentCases.length === 1 ? "case" : "cases"})</span></h3>
        <p className="caption mt-1">{AGENT_COL_TIP}. Open a case for each check and its evidence.</p>
        <AgentCases cases={d.agentCases} emptyText="Not wired yet — no agent cases ran for this skill." />
      </section>
    </>
  );
}
