"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { CatalogRow } from "@/lib/data";
import { skillHref } from "@/lib/data";
import { matchesVerdictFilter, verdictSeverity, type VerdictFilter } from "@/lib/verdict";
import { VerdictBadge, Lift, Trig } from "./Badge";
import { DomainFilter, VerdictFilterControl } from "./FilterBar";
import { COL_TIPS } from "./DomainTable";

export function CatalogTable({ rows, domains }: { rows: CatalogRow[]; domains: string[] }) {
  const router = useRouter();
  const [dom, setDom] = useState<string>("all");
  const [ver, setVer] = useState<VerdictFilter>("all");
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows
      .filter((r) =>
        (dom === "all" || r.domain === dom) &&
        matchesVerdictFilter(ver, r.verdict) &&
        (!needle || r.name.toLowerCase().includes(needle) || r.description.toLowerCase().includes(needle)))
      .sort((a, b) => verdictSeverity(a.verdict) - verdictSeverity(b.verdict) || (a.lift ?? 0) - (b.lift ?? 0) || a.name.localeCompare(b.name));
  }, [rows, dom, ver, q]);

  return (
    <div className="flex flex-col gap-5">
      <div className="card toolbar">
        <input className="input" type="search" placeholder="Search name or description" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search skills" />
        <DomainFilter id="cat-domain" domains={domains} value={dom} onChange={setDom} />
        <VerdictFilterControl id="cat-verdict" value={ver} onChange={setVer} />
        <span className="toolbar-count">{filtered.length} of {rows.length} skills · worst first</span>
      </div>

      <div className="card">
        <table className="tbl only-desktop">
          <thead>
            <tr>
              <th>Skill</th>
              <th>Domain</th>
              <th>Verdict</th>
              <th className="num" title={COL_TIPS.lift}>Lift</th>
              <th className="num" title={COL_TIPS.trigger}>Trigger</th>
              <th style={{ width: "40%" }}>Description</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.id} className="clickable" onClick={() => router.push(skillHref(r.id))} tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push(skillHref(r.id)); } }}>
                <td><Link href={skillHref(r.id)} className="cell-name" onClick={(e) => e.stopPropagation()}>{r.name}</Link></td>
                <td><span className="domain-tag">{r.domain}</span></td>
                <td><VerdictBadge v={r.verdict} /></td>
                <td className="num"><Lift n={r.lift} /></td>
                <td className="num"><Trig n={r.triggerAcc} /></td>
                <td className="desc" title={r.description}><span>{r.description}</span></td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={6} className="none">No skills match.</td></tr>}
          </tbody>
        </table>

        <div className="row-list only-mobile">
          {filtered.map((r) => (
            <Link key={r.id} href={skillHref(r.id)} className="row-card">
              <div className="row-card-top">
                <span className="row-card-name">{r.name}</span>
                <VerdictBadge v={r.verdict} small />
              </div>
              <div className="row-card-meta">
                <span>{r.domain}</span>
                <span>Lift <b><Lift n={r.lift} /></b></span>
                <span>Trigger <b><Trig n={r.triggerAcc} /></b></span>
              </div>
              <div className="row-card-desc">{r.description}</div>
            </Link>
          ))}
          {filtered.length === 0 && <div className="row-card none">No skills match.</div>}
        </div>
      </div>
    </div>
  );
}
