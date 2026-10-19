import Link from "next/link";
import { notFound } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { getCatalogEntity, listEntityResults, type ScorecardResultRow } from "@/lib/db/catalog";
import { PageHead } from "@/components/PageHead";
import { ScoreAll } from "@/components/catalog/ScoreAll";
import { CHECKS } from "@/lib/scorecards/checks";
import { mdToHtml } from "@/lib/markdown.mjs";
import { humanName } from "@/lib/names";

export const dynamic = "force-dynamic";
export const maxDuration = 60;
const CLS: Record<string, string> = { pass: "pill-sage", warn: "pill-hold", fail: "pill-rust", error: "pill-rust", skipped: "" };
type Res = ScorecardResultRow;

/** One repository's scorecard: each check's verdict, the skill's own report as evidence, and the history. */
export default async function EntityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/.test(id)) notFound();
  const ctx = await requireWorkspace();
  const e = await getCatalogEntity(ctx.supabase, ctx.workspace.id, id);
  if (!e) notFound();
  const all = await listEntityResults(ctx.supabase, ctx.workspace.id, id);
  const latest = CHECKS.map((c) => all.find((r) => r.check_id === c.id)).filter((r): r is Res => !!r);
  const canScore = ctx.role === "admin" || ctx.role === "author";
  const when = (iso: string) => new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
  return (
    <>
      <PageHead eyebrow="Catalog · scorecard" title="" em={e.key.split("/")[1]} lead={`${e.key} — each check runs a library skill on the repository's real files at the commit shown; the verdict is the skill's own.`} />
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <a className="link" href={e.url} target="_blank" rel="noreferrer">Open on GitHub</a>
        <Link className="link" href="/catalog">Back to catalog</Link>
        {canScore && <ScoreAll entities={[{ id: e.id, key: e.key }]} label="Re-run this scorecard" />}
      </div>
      {latest.length === 0 && <p className="none">Not scored yet.</p>}
      {latest.map((r) => (
        <section key={r.id} className="card card-pad mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="h3" style={{ margin: 0 }}>{CHECKS.find((c) => c.id === r.check_id)?.title ?? r.check_id} <span className={`pill pill-sm ${CLS[r.verdict] ?? ""}`}>{r.verdict}</span></div>
            <span className="caption">{when(r.created_at)}{r.commit_sha ? <> · commit <a className="link" href={`${e.url}/commit/${r.commit_sha}`} target="_blank" rel="noreferrer"><code>{r.commit_sha.slice(0, 7)}</code></a></> : null} · {r.details.files_used ?? 0} files · {Math.round((r.duration_ms ?? 0) / 100) / 10}s</span>
          </div>
          <p style={{ margin: "6px 0" }}>{r.summary}</p>
          <p className="caption" style={{ margin: 0 }}>By the <Link className="link" href={`/repo/${r.skill}`}>{humanName(r.skill.split("/")[1])}</Link> skill.{r.details.partial ? " Partial scan: the repository is larger than the scan limit." : ""}</p>
          {r.verdict === "error" && r.details.log_tail && (
            <details className="mt-3"><summary className="caption">What the skill printed</summary><pre className="run-raw">{r.details.log_tail}</pre></details>)}
          {r.details.report && (
            <details className="mt-3"><summary className="caption">The skill&apos;s report</summary>
              {/\.md$|^#/m.test(r.details.report) ? <div className="prose run-prose" dangerouslySetInnerHTML={{ __html: mdToHtml(r.details.report) }} /> : <pre className="run-raw">{r.details.report}</pre>}
            </details>)}
        </section>
      ))}
      {all.length > latest.length && (
        <section className="section">
          <div className="h3">History</div>
          <div className="tablewrap"><table className="mini"><thead><tr><th>When</th><th>Check</th><th>Verdict</th><th>Summary</th><th>Commit</th></tr></thead>
            <tbody>{all.map((r) => <tr key={r.id}><td className="caption">{when(r.created_at)}</td><td>{CHECKS.find((c) => c.id === r.check_id)?.title.split(" (")[0] ?? r.check_id}</td>
              <td><span className={`pill pill-sm ${CLS[r.verdict] ?? ""}`}>{r.verdict}</span></td><td className="ink-2">{r.summary}</td><td><code>{r.commit_sha?.slice(0, 7) ?? "—"}</code></td></tr>)}</tbody></table></div>
        </section>)}
    </>
  );
}
