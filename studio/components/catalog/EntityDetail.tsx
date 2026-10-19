import Link from "next/link";
import { PageHead } from "@/components/PageHead";
import { LocalTime } from "@/components/LocalTime";
import { RELATION_LABEL, type EntityRow, type RelatedRow } from "@/lib/db/entities";

const KIND_LABEL: Record<string, string> = { repository: "Repository", service: "Service", database: "Database" };
const SOURCE_LABEL: Record<string, string> = { github: "GitHub", vercel: "Vercel", supabase: "Supabase" };
const HIDE = new Set(["prod_deploys"]);

/** Relations of an entity, grouped by how they read from this end, each with the evidence it was learned from. */
export function RelatedList({ rels }: { rels: RelatedRow[] }) {
  if (!rels.length) return <p className="caption" style={{ margin: 0 }}>No relations yet.</p>;
  return (
    <ul className="ini-repos">{rels.map((r) => (
      <li key={`${r.relation}-${r.direction}-${r.other.id}`}>
        <span className="caption">{RELATION_LABEL[r.relation]?.[r.direction] ?? r.relation}</span>{" "}
        <Link className="link" href={`/catalog/${r.other.id}`}>{r.other.kind === "repository" ? r.other.key : r.other.title}</Link>{" "}
        <span className="caption">({KIND_LABEL[r.other.kind] ?? r.other.kind}) — {r.evidence}</span>
      </li>))}</ul>
  );
}

const show = (v: unknown): React.ReactNode => {
  if (v == null || v === "") return <span className="caption">—</span>;
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) return <LocalTime iso={v} />;
  if (typeof v === "string" && /^https:\/\//.test(v)) return <a className="link" href={v} target="_blank" rel="noreferrer">{v.replace("https://", "")}</a>;
  if (typeof v === "object") return <code className="mono-sm">{JSON.stringify(v).slice(0, 300)}</code>;
  return String(v);
};

/** A service or database: what the provider reports, and how it relates to the rest of the catalog. */
export function EntityDetail({ e, rels }: { e: EntityRow; rels: RelatedRow[] }) {
  const props = Object.entries(e.properties).filter(([k]) => !HIDE.has(k));
  const deploys = (e.properties.prod_deploys as string[] | undefined) ?? null;
  return (
    <>
      <PageHead eyebrow={`Catalog · ${KIND_LABEL[e.kind] ?? e.kind}`} title="" em={e.title} lead={`From ${SOURCE_LABEL[e.source] ?? e.source}. Read-only: the catalog reflects the provider, it does not change it.`} />
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <a className="link" href={e.url} target="_blank" rel="noreferrer">Open in {SOURCE_LABEL[e.source] ?? e.source}</a>
        <Link className="link" href={`/catalog?type=${e.kind}`}>All {e.kind === "service" ? "services" : "databases"}</Link>
      </div>
      <section className="card card-pad mb-4"><div className="h3" style={{ marginTop: 0 }}>Related</div><RelatedList rels={rels} /></section>
      <section className="card card-pad mb-4">
        <div className="h3" style={{ marginTop: 0 }}>Properties</div>
        <dl className="kv">{props.map(([k, v]) => <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{show(v)}</dd></div>)}</dl>
        {deploys && <p className="caption" style={{ margin: "8px 0 0" }}>{deploys.length} successful production deployment{deploys.length === 1 ? "" : "s"} in the last 90 days{deploys.length ? <>, newest <LocalTime iso={deploys[0]} /></> : ""}.</p>}
      </section>
    </>
  );
}
