import Link from "next/link";

const PLACES: [string, string, string][] = [
  ["/library/", "Library", "every skill the portal ships"],
  ["/pipeline", "Publish pipeline", "your workspace's skills, by release gate"],
  ["/catalog", "Catalog", "repositories, services and databases"],
  ["/assistant", "Assistant", "ask where something is"],
  ["/glossary", "Glossary", "what each name means"],
];

export default function NotFound() {
  return (
    <div className="page-head">
      <div className="eyebrow">404</div>
      <h1 className="h1">Nothing <em>here</em>.</h1>
      <p className="sub">This address is not a page in the portal. It may be an old link. These are the likeliest places you meant:</p>
      <ul className="stack mt-3" style={{ listStyle: "none", padding: 0 }}>
        {PLACES.map(([href, label, what]) => (
          <li key={href}><Link href={href} className="link-flame">{label} →</Link> <span className="caption">{what}</span></li>
        ))}
      </ul>
    </div>
  );
}
