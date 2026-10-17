/** Eyebrow + serif h1 (with an italic flame emphasis) + one-line subtitle. */
export function PageHead({ eyebrow, title, em, after, sub }: {
  eyebrow: string; title: string; em: string; after?: string; sub?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div className="eyebrow">{eyebrow}</div>
      <h1 className="h1">{title} <em>{em}</em>{after ?? "."}</h1>
      {sub && <p className="sub">{sub}</p>}
    </div>
  );
}

export function SectionHead({ eyebrow, title, em, right }: { eyebrow?: string; title: string; em?: string; right?: React.ReactNode }) {
  return (
    <div className="section-head">
      <div>
        {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
        <h2 className="h2">{title}{em && <> <em>{em}</em></>}</h2>
      </div>
      {right}
    </div>
  );
}

export function StatStrip({ stats }: { stats: { label: string; value: React.ReactNode }[] }) {
  return (
    <div className="stats" role="list">
      {stats.map((s) => (
        <div key={s.label} className="stat" role="listitem">
          <div className="stat-value">{s.value}</div>
          <div className="stat-label">{s.label}</div>
        </div>
      ))}
    </div>
  );
}
