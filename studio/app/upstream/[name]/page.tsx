import { humanName } from "@/lib/names";
import Link from "next/link";
import { notFound } from "next/navigation";
import { upstream, upstreamFor, categoryLabel, licenseLabel } from "@/lib/data";
import { LicensePill } from "@/components/Badge";
import { StatStrip } from "@/components/PageHead";

/** "3.9M installs (https://skills.sh/x/y)" → "3.9M installs" linking to skills.sh; anything else verbatim. */
function Evidence({ text }: { text: string }) {
  const m = text.match(/^(.*?)\s*\((https?:\/\/[^)\s]+)\)\s*$/);
  if (!m) return <>{text}</>;
  return <a href={m[2]} className="link" target="_blank" rel="noopener">{m[1]}</a>;
}

export function generateStaticParams() {
  return upstream.map((u) => ({ name: u.name }));
}
export const dynamicParams = false;

export async function generateMetadata({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return { title: `${humanName(name)} · Reference skills · Skills Factory` };
}

export default async function UpstreamSkillPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const u = upstreamFor(name);
  if (!u) notFound();
  const sourceAvailable = u.licenseKind === "source-available";

  return (
    <>
      <div className="page-head">
        <nav className="caption" aria-label="Breadcrumb">
          <Link href="/upstream/" className="link">Reference skills</Link> <span aria-hidden="true">›</span> {u.name}
        </nav>
        <div className="eyebrow mt-5">{u.name}</div>
        <h1 className="h1" style={{ marginBottom: 12 }}>{u.name.replace(/-/g, " ")}</h1>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <LicensePill u={u} />
          <span className="caption">{u.origin === "vendor" ? "Vendor team" : "Community"} · <Evidence text={u.evidence} /></span>
        </div>
        <p className="lead mt-5">{u.description}</p>
      </div>

      <div className="card card-pad">
        <StatStrip stats={[
          { label: "Rank", value: <>#{u.rank}</>, title: u.evidence },
          { label: "Category", value: <span className="stat-text">{categoryLabel(u.category)}</span> },
          { label: "License", value: <span className="stat-text">{licenseLabel(u)}</span>, title: u.license },
          { label: "Pinned", value: <span className="stat-text mono">{u.shortSha}</span>, title: u.sha },
          { label: "Files", value: u.fileCount },
        ]} />
      </div>

      <div className="two-col mt-7">
        <div className="card card-pad min-w-0">
          <div className="eyebrow mb-4">SKILL.md</div>
          {sourceAvailable || !u.bodyHtml
            ? <p className="ink-2">Not shown here: this skill is Anthropic source-available and may not be redistributed. Read it at the source (link on the right) under your Anthropic agreement.</p>
            : <div className="prose" dangerouslySetInnerHTML={{ __html: u.bodyHtml }} />}
        </div>
        <aside className="sidebar">
          <div className="card card-pad">
            <div className="h3 mb-3">Source</div>
            <a href={u.url} className="btn btn-secondary w-full mb-4" target="_blank" rel="noopener">View on GitHub ↗</a>
            <dl className="src-list">
              <dt>Repo</dt><dd className="mono">{u.repo}</dd>
              <dt>Path</dt><dd className="mono">{u.path}</dd>
              <dt>Commit</dt><dd className="mono" title={u.sha}>{u.shortSha}</dd>
              <dt>Fetched</dt><dd>{u.fetched ?? "—"}</dd>
              <dt>License</dt><dd>{u.license}</dd>
            </dl>
            <p className={`caption mt-4 ${sourceAvailable ? "license-note license-note-hold" : "license-note"}`}>
              {sourceAvailable
                ? <>Anthropic source-available. Governed by your Anthropic agreement; do not redistribute publicly.</>
                : <>Open source under {licenseLabel(u)}. Keep the upstream license file with any copy.</>}
            </p>
          </div>
          <div className="card card-pad">
            <div className="h3 mb-2">Why it is here</div>
            <p className="ink-2 text-[14px] leading-relaxed">{u.why}</p>
          </div>
        </aside>
      </div>
    </>
  );
}
