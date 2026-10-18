/** Eyebrow + serif h1 (with an italic flame emphasis) + the one-sentence answer to the view's question. */
export function PageHead({ eyebrow, title, em, after, lead, caption, note }: {
  eyebrow: string; title: string; em: string; after?: string; lead?: React.ReactNode; caption?: React.ReactNode;
  /** One-line pointer under the caption (a sibling view, a related page). */
  note?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div className="eyebrow">{eyebrow}</div>
      <h1 className="h1">{title} <em>{em}</em>{after ?? "."}</h1>
      {lead && <p className="lead">{lead}</p>}
      {caption && <p className="caption mt-3">{caption}</p>}
      {note && <p className="page-note">{note}</p>}
    </div>
  );
}

export function SectionHead({ id, title, em, caption, right }: { id?: string; title: string; em?: string; caption?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="section-head" id={id}>
      <div>
        <h2 className="h2">{title}{em && <> <em>{em}</em></>}</h2>
        {caption && <p className="caption">{caption}</p>}
      </div>
      {right}
    </div>
  );
}

export function StatStrip({ stats }: { stats: { label: string; value: React.ReactNode; title?: string }[] }) {
  return (
    <div className="stats" role="list">
      {stats.map((s) => (
        <div key={s.label} className="stat" role="listitem" title={s.title}>
          <div className="stat-value">{s.value}</div>
          <div className="stat-label">{s.label}</div>
        </div>
      ))}
    </div>
  );
}
