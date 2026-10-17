"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { CatalogRow, Verdict } from "@/lib/data";
import { skillHref } from "@/lib/data";
import { VerdictBadge, Lift, Trig } from "./Badge";
import { Chips } from "./Chips";

export function CatalogTable({ rows, domains, verdicts }: { rows: CatalogRow[]; domains: string[]; verdicts: Verdict[] }) {
  const router = useRouter();
  const [dom, setDom] = useState<Set<string>>(new Set());
  const [ver, setVer] = useState<Set<Verdict>>(new Set());
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((r) =>
      (dom.size === 0 || dom.has(r.domain)) &&
      (ver.size === 0 || (r.verdict && ver.has(r.verdict))) &&
      (!needle || r.name.toLowerCase().includes(needle) || r.description.toLowerCase().includes(needle)),
    );
  }, [rows, dom, ver, q]);

  return (
    <div className="flex flex-col gap-5">
      <div className="card toolbar">
        <input className="input" type="search" placeholder="search name + description" value={q} onChange={(e) => setQ(e.target.value)} aria-label="search skills" />
        <Chips label="domain" options={domains} value={dom} onChange={setDom} />
        <Chips label="verdict" options={verdicts} value={ver} onChange={setVer} />
        <span className="toolbar-count">{filtered.length} of {rows.length}</span>
      </div>
      <div className="card tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th>Skill</th><th>Domain</th><th>Verdict</th>
              <th className="num">Trigger</th><th className="num">Lift</th><th className="num">Cases</th><th className="num">Scripts</th>
              <th className="wrap" style={{ width: "42%" }}>Description</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.id} className="clickable" onClick={() => router.push(skillHref(r.id))}>
                <td><Link href={skillHref(r.id)} className="cell-name" onClick={(e) => e.stopPropagation()}>{r.name}</Link></td>
                <td><span className="tag">{r.domain}</span></td>
                <td><VerdictBadge v={r.verdict} /></td>
                <td className="num"><Trig n={r.triggerAcc} /></td>
                <td className="num"><Lift n={r.lift} /></td>
                <td className="num">{r.cases}</td>
                <td className="num">{r.scripts || <span className="muted">0</span>}</td>
                <td className="truncate-1 ink-2" title={r.description}>{r.description}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={8} className="none">No skills match.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
