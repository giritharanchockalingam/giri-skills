"use client";
import { matches } from "@/lib/search";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { UpstreamSkill, LicenseFilter } from "@/lib/data";
import { upstreamHref, categoryLabel, LICENSE_FILTERS } from "@/lib/data";
import { ChoiceFilter } from "./FilterBar";
import { LicensePill } from "./Badge";

export function UpstreamTable({ rows, categories }: { rows: UpstreamSkill[]; categories: string[] }) {
  const router = useRouter();
  const [cat, setCat] = useState<string>("all");
  const [lic, setLic] = useState<LicenseFilter | "all">("all");
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows
      .filter((r) =>
        (cat === "all" || r.category === cat) &&
        (lic === "all" || r.licenseKind === lic) &&
        matches(needle, r.name, r.description, r.repo))
      .sort((a, b) => a.rank - b.rank);
  }, [rows, cat, lic, q]);

  const go = (name: string) => router.push(upstreamHref(name));
  const stop = (e: React.MouseEvent) => e.stopPropagation();

  return (
    <div className="flex flex-col gap-5">
      <div className="card toolbar">
        <input className="input" type="search" placeholder="Search name, description or repo" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search upstream skills" />
        <ChoiceFilter id="up-category" label="Category" allLabel="All categories" value={cat} onChange={setCat}
          options={categories.map((c) => ({ key: c, label: categoryLabel(c) }))} />
        <ChoiceFilter id="up-license" label="License" allLabel="All" value={lic} onChange={setLic}
          options={LICENSE_FILTERS.filter((f) => f.key !== "all").map((f) => ({ key: f.key, label: f.label }))} />
        <span className="toolbar-count">{filtered.length} of {rows.length} skills · by installs</span>
      </div>

      <div className="card">
        <div className="tablewrap"><table className="tbl up-tbl only-desktop">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Skill</th>
              <th>Source</th>
              <th>Category</th>
              <th>License</th>
              <th title="Upstream commit the vendored copy was taken from">Pinned</th>
              <th className="col-why">Why</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.name} className="clickable" onClick={() => go(r.name)} tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(r.name); } }}>
                <td className="num rank">{r.rank}</td>
                <td><Link href={upstreamHref(r.name)} className="cell-name" onClick={stop}>{r.name}</Link></td>
                <td><a href={r.url} className="repo-link" target="_blank" rel="noopener" onClick={stop} title={`${r.repo}/${r.path} @ ${r.shortSha}`}>{r.repo}</a></td>
                <td><span className="domain-tag">{categoryLabel(r.category)}</span></td>
                <td><LicensePill u={r} /></td>
                <td><span className="sha" title={r.sha}>{r.shortSha}</span></td>
                <td className="desc desc-1" title={r.why}><span>{r.why}</span></td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={7} className="none">No skills match.</td></tr>}
          </tbody>
        </table></div>

        <div className="row-list only-mobile">
          {filtered.map((r) => (
            <Link key={r.name} href={upstreamHref(r.name)} className="row-card">
              <div className="row-card-top">
                <span className="row-card-name"><span className="rank-sm">{r.rank}</span>{r.name}</span>
                <LicensePill u={r} small />
              </div>
              <div className="row-card-meta">
                <span className="mono">{r.repo}</span>
                <span>{categoryLabel(r.category)}</span>
                <span className="mono">{r.shortSha}</span>
              </div>
              <div className="row-card-desc">{r.why}</div>
            </Link>
          ))}
          {filtered.length === 0 && <div className="row-card none">No skills match.</div>}
        </div>
      </div>
    </div>
  );
}
