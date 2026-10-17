"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { CatalogRow, Verdict } from "@/lib/data";
import { skillHref } from "@/lib/data";
import { VerdictBadge, Lift } from "./Badge";
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

  const trunc = (s: string, n = 140) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <input className="input" type="search" placeholder="search name + description" value={q} onChange={(e) => setQ(e.target.value)} aria-label="search skills" />
        <Chips label="domain" options={domains} value={dom} onChange={setDom} />
        <Chips label="verdict" options={verdicts} value={ver} onChange={setVer} />
        <span className="mono ml-auto text-[11.5px] text-fg-3">{filtered.length} of {rows.length}</span>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th>name</th><th>domain</th><th>verdict</th>
              <th className="num">trigger</th><th className="num">lift</th><th className="num">cases</th><th className="num">scripts</th>
              <th className="wrap">description</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.id} className="clickable" onClick={() => router.push(skillHref(r.id))}>
                <td className="mono"><Link href={skillHref(r.id)} onClick={(e) => e.stopPropagation()}>{r.name}</Link></td>
                <td className="text-fg-2">{r.domain}</td>
                <td><VerdictBadge v={r.verdict} /></td>
                <td className="num">{r.triggerAcc == null ? "—" : r.triggerAcc.toFixed(2)}</td>
                <td className="num"><Lift n={r.lift} /></td>
                <td className="num">{r.cases}</td>
                <td className="num">{r.scripts || <span className="muted">0</span>}</td>
                <td className="wrap min-w-[360px] text-fg-2" title={r.description}>{trunc(r.description)}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={8} className="muted">no skills match</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
