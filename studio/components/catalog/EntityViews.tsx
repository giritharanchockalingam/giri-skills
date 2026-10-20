import Link from "next/link";
import { LocalTime } from "@/components/LocalTime";
import type { EntityRow } from "@/lib/db/entities";

type Rel = { from: string; to: string; type: string; evidence: string };
const STATE: Record<string, string> = { READY: "pill-sage", ERROR: "pill-rust", CANCELED: "", BUILDING: "pill-hold", ACTIVE_HEALTHY: "pill-sage" };

/** Catalog type switcher (Port's blueprints): repositories, services, databases — each with its count. */
export function KindTabs({ active, counts }: { active: "repository" | "service" | "database" | "component"; counts: Record<string, number> }) {
  const tabs = [["repository", "Repositories", "/catalog"], ["service", "Services", "/catalog?type=service"], ["database", "Databases", "/catalog?type=database"] ] as const;
  return (
    <nav className="subnav" aria-label="Entity types">
      {tabs.map(([k, label, href]) => <Link key={k} href={href} aria-current={active === k ? "page" : undefined}>{label}<span className="tab-count">{counts[k] ?? 0}</span></Link>)}
      <Link href="/integrations">Integrations</Link>
    </nav>
  );
}

export function ServicesTable({ rows, all, rels }: { rows: EntityRow[]; all: Map<string, EntityRow>; rels: Rel[] }) {
  return (
    <div className="card"><div className="tablewrap"><table className="mini cat-table">
      <thead><tr><th>Service</th><th>Built from</th><th>Production</th><th>Last production deploy</th><th>Deploys (30 d)</th><th>Uses database</th></tr></thead>
      <tbody>{rows.map((s) => {
        const p = s.properties as { framework?: string | null; production_url?: string | null; repo?: string | null; last_deploy?: { state: string | null; at: string | null; sha: string | null } | null; deploys_30d?: number; failed_30d?: number };
        const repo = rels.filter((r) => r.from === s.id && r.type === "built_from").map((r) => all.get(r.to)).find(Boolean);
        const dbs = rels.filter((r) => r.from === s.id && r.type === "uses_database").map((r) => all.get(r.to)).filter((x): x is EntityRow => !!x);
        return (
          <tr key={s.id}>
            <td><Link className="link" href={`/catalog/${s.id}`}><b>{s.title}</b></Link>{p.framework && <div className="caption">{p.framework}</div>}</td>
            <td>{repo ? <Link className="link" href={`/catalog/${repo.id}`}>{repo.key}</Link> : p.repo ? <span className="caption">{p.repo} (not in the catalog)</span> : <span className="caption">no Git link</span>}</td>
            <td>{p.production_url ? <a className="link caption" href={p.production_url} target="_blank" rel="noreferrer">{p.production_url.replace("https://", "")}</a> : <span className="caption">—</span>}</td>
            <td>{p.last_deploy ? <><span className={`pill pill-sm ${STATE[p.last_deploy.state ?? ""] ?? ""}`}>{(p.last_deploy.state ?? "?").toLowerCase()}</span> <span className="caption"><LocalTime iso={p.last_deploy.at} />{p.last_deploy.sha ? ` · ${p.last_deploy.sha.slice(0, 7)}` : ""}</span></> : <span className="caption">none in 90 days</span>}</td>
            <td>{p.deploys_30d ?? 0}{p.failed_30d ? <span className="caption ink-rust"> · {p.failed_30d} failed</span> : null}</td>
            <td>{dbs.length ? dbs.map((d) => <div key={d.id}><Link className="link" href={`/catalog/${d.id}`}>{d.title}</Link></div>) : <span className="caption">—</span>}</td>
          </tr>);
      })}</tbody>
    </table></div></div>
  );
}

export function DatabasesTable({ rows, all, rels }: { rows: EntityRow[]; all: Map<string, EntityRow>; rels: Rel[] }) {
  return (
    <div className="card"><div className="tablewrap"><table className="mini cat-table">
      <thead><tr><th>Database</th><th>Status</th><th>Region</th><th>Postgres</th><th>Used by</th></tr></thead>
      <tbody>{rows.map((d) => {
        const p = d.properties as { region?: string | null; status?: string | null; postgres?: string | null };
        const users = rels.filter((r) => r.to === d.id && r.type === "uses_database").map((r) => all.get(r.from)).filter((x): x is EntityRow => !!x);
        return (
          <tr key={d.id}>
            <td><Link className="link" href={`/catalog/${d.id}`}><b>{d.title}</b></Link><div className="caption"><code>{d.key}</code></div></td>
            <td><span className={`pill pill-sm ${STATE[p.status ?? ""] ?? ""}`}>{(p.status ?? "unknown").toLowerCase().replace(/_/g, " ")}</span></td>
            <td className="caption">{p.region ?? "—"}</td>
            <td className="caption">{p.postgres ?? "—"}</td>
            <td>{users.length ? users.map((u) => <div key={u.id}><Link className="link" href={`/catalog/${u.id}`}>{u.title}</Link></div>) : <span className="caption">no service points at it</span>}</td>
          </tr>);
      })}</tbody>
    </table></div></div>
  );
}

/** Everything else the connected tools know (pull requests, CI workflows, deployments, environments, teams…), grouped
 *  by type, each linked to its own page and to the catalog entries it relates to. */
export function ComponentsTable({ rows, all, rels, type }: { rows: EntityRow[]; all: Map<string, EntityRow>; rels: Rel[]; type: string | null }) {
  const types = new Map<string, number>();
  for (const r of rows) { const t = String(r.properties.type ?? "Other"); types.set(t, (types.get(t) ?? 0) + 1); }
  const shown = type ? rows.filter((r) => String(r.properties.type ?? "Other") === type) : rows;
  return (
    <>
      <div className="chip-group mb-3" role="navigation" aria-label="Component types">
        <Link className="chip" href="/catalog?type=component" aria-pressed={!type}>All <span className="tab-count">{rows.length}</span></Link>
        {[...types.entries()].sort((a, b) => b[1] - a[1]).map(([t, n]) => <Link key={t} className="chip" href={`/catalog?type=component&of=${encodeURIComponent(t)}`} aria-pressed={type === t}>{t} <span className="tab-count">{n}</span></Link>)}
      </div>
      <div className="card"><div className="tablewrap"><table className="mini cat-table">
        <thead><tr><th>Name</th><th>Type</th><th>Details</th><th>Related to</th><th>Updated</th></tr></thead>
        <tbody>{shown.slice(0, 500).map((c) => {
          const facts = ((c.properties.facts ?? []) as { label: string; value: string }[]).slice(0, 3);
          const related = rels.filter((r) => r.type === "related" && (r.from === c.id || r.to === c.id)).map((r) => all.get(r.from === c.id ? r.to : r.from)).filter((x): x is EntityRow => !!x).slice(0, 3);
          return (
            <tr key={c.id}>
              <td><Link className="link" href={`/catalog/${c.id}`}><b>{c.title}</b></Link></td>
              <td><span className="pill pill-sm">{String(c.properties.type ?? "Other")}</span></td>
              <td className="caption">{facts.length ? facts.map((f) => <div key={f.label}><span className="muted">{f.label}:</span> {/^\d{4}-\d{2}-\d{2}T/.test(f.value) ? <LocalTime iso={f.value} /> : f.value}</div>) : "—"}</td>
              <td className="caption">{related.length ? related.map((r) => <div key={r.id}><Link className="link" href={`/catalog/${r.id}`}>{r.title}</Link></div>) : "—"}</td>
              <td className="caption"><LocalTime iso={c.last_activity_at} /></td>
            </tr>);
        })}</tbody>
      </table></div></div>
      {shown.length > 500 && <p className="caption mt-2">Showing the 500 most recently updated of {shown.length}.</p>}
    </>
  );
}
