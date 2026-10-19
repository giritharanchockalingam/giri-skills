import { LocalTime } from "@/components/LocalTime";
import Link from "next/link";
import { notFound } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { getCatalogEntity, listEntityResults, type ScorecardResultRow } from "@/lib/db/catalog";
import { PageHead } from "@/components/PageHead";
import { ScoreAll } from "@/components/catalog/ScoreAll";
import { CHECKS } from "@/lib/scorecards/checks";
import { mdToHtml } from "@/lib/markdown.mjs";
import { humanName } from "@/lib/names";
import { levelOf, factsOf, LEVEL_LABEL, LEVEL_RULE } from "@/lib/scorecards/levels";
import { LevelBadge } from "@/components/catalog/LevelBadge";
import { ActionPanel } from "@/components/catalog/ActionPanel";
import { listActions } from "@/lib/db/actions";
import { getPolicy } from "@/lib/factory/db";
import { loadDelivery } from "@/lib/db/delivery";
import { getEntity, relationsOf } from "@/lib/db/entities";
import { EntityDetail, RelatedList } from "@/components/catalog/EntityDetail";
import { DeliveryTable } from "@/components/insights/DeliveryTable";

export const dynamic = "force-dynamic";
export const metadata = { title: "Catalog · Skills Factory" };
export const maxDuration = 60;
const CLS: Record<string, string> = { pass: "pill-sage", warn: "pill-hold", fail: "pill-rust", error: "pill-rust", skipped: "" };
type Res = ScorecardResultRow;
const ACTION_CLS: Record<string, string> = { succeeded: "pill-sage", failed: "pill-rust", rejected: "pill-rust", pending_approval: "pill-hold", running: "", approved: "" };

/** One repository's scorecard: each check's verdict, the skill's own report as evidence, and the history. */
export default async function EntityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/.test(id)) notFound();
  const ctx = await requireWorkspace();
  const [any, rels] = await Promise.all([getEntity(ctx.supabase, ctx.workspace.id, id), relationsOf(ctx.supabase, ctx.workspace.id, id)]);
  if (!any) notFound();
  if (any.kind !== "repository") return <EntityDetail e={any} rels={rels} />;
  const e = await getCatalogEntity(ctx.supabase, ctx.workspace.id, id);
  if (!e) notFound();
  const all = await listEntityResults(ctx.supabase, ctx.workspace.id, id);
  const latest = CHECKS.map((c) => all.find((r) => r.check_id === c.id)).filter((r): r is Res => !!r);
  const canScore = ctx.role === "admin" || ctx.role === "author";
  const lv = levelOf(factsOf(e.properties), latest);
  const [actions, policy, delivery] = await Promise.all([listActions(ctx.supabase, ctx.workspace.id, { entityId: id, limit: 10 }), getPolicy(ctx), loadDelivery(ctx.supabase, ctx.workspace.id, id)]);
  return (
    <>
      <PageHead eyebrow="Catalog · scorecard" title="" em={e.key.split("/")[1]} lead={`${e.key} — each check runs a library skill on the repository's real files at the commit shown; the verdict is the skill's own.`} />
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <a className="link" href={e.url} target="_blank" rel="noreferrer">Open on GitHub</a>
        <Link className="link" href="/catalog">Back to catalog</Link>
        {canScore && <ScoreAll entities={[{ id: e.id, key: e.key }]} label="Re-run this scorecard" />}
      </div>
      {rels.length > 0 && <section className="card card-pad mb-4"><div className="h3" style={{ marginTop: 0 }}>Related</div><RelatedList rels={rels} /></section>}
      <section className="card card-pad mb-4 level-panel">
        <div className="flex flex-wrap items-center gap-3"><LevelBadge level={lv.level} large /><span className="caption">{lv.level === "n/a" ? <>No scorecard check applies: today&apos;s checks cover Supabase migrations and Next.js apps, and this repository has neither. Nothing to fix; it gets a level once it adds either. <Link className="link" href="/glossary">What levels mean</Link></> : `${lv.applicable.length} check${lv.applicable.length === 1 ? "" : "s"} apply.`}</span></div>
        {lv.next && (<>
          <p style={{ margin: "10px 0 4px" }}>To reach <b>{LEVEL_LABEL[lv.next]}</b> ({LEVEL_RULE[lv.next]}):</p>
          <ul className="level-blockers">{lv.blockers.map((b) => <li key={b.check_id}><b>{b.title}</b> — {b.reason}</li>)}</ul>
        </>)}
        {lv.level === "gold" && <p className="caption" style={{ margin: "8px 0 0" }}>Every applicable check passes.</p>}
      </section>
      {delivery.length > 0 && (
        <section className="card card-pad mb-4" id="delivery">
          <div className="h3" style={{ marginTop: 0 }}>Delivery — last 30 days</div>
          <DeliveryTable rows={delivery} window={30} />
          <p className="caption" style={{ margin: "6px 0 0" }}>Definitions and 90-day view on <Link className="link" href="/insights?days=90#delivery">Insights</Link>.</p>
        </section>)}
      <section className="card card-pad mb-4" id="actions">
        <div className="h3" style={{ marginTop: 0 }}>Run a skill on this repository</div>
        <ActionPanel entityId={e.id} repo={e.key} approvalRule={policy?.action_approval ?? "model_steps"} />
        {actions.length > 0 && (
          <div className="tablewrap mt-4"><table className="mini"><thead><tr><th>When</th><th>Skill</th><th>Status</th><th>By</th><th>Result</th></tr></thead>
            <tbody>{actions.map((a) => <tr key={a.id}><td className="caption"><LocalTime iso={a.created_at} /></td><td>{a.skill}</td>
              <td><span className={`pill pill-sm ${ACTION_CLS[a.status] ?? ""}`}>{a.status.replace("_", " ")}</span></td>
              <td className="caption">{a.requested_by_email ?? "—"}{a.decided_by_email ? ` · decided by ${a.decided_by_email}` : ""}</td>
              <td>{a.run_id ? <><Link className="link" href={`/runs/${a.run_id}`}>run</Link>{a.error && <div className={`caption${a.status === "failed" ? " ink-rust" : ""}`}>{a.error}</div>}</> : a.error ? <span className="caption ink-rust">{a.error}</span> : <span className="caption">—</span>}</td></tr>)}</tbody></table></div>)}
      </section>
      {latest.length === 0 && <p className="none">Not scored yet.</p>}
      {latest.map((r) => (
        <section key={r.id} className="card card-pad mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="h3" style={{ margin: 0 }}>{CHECKS.find((c) => c.id === r.check_id)?.title ?? r.check_id} <span className={`pill pill-sm ${CLS[r.verdict] ?? ""}`}>{r.verdict}</span></div>
            <span className="caption"><LocalTime iso={r.created_at} />{r.commit_sha ? <> · commit <a className="link" href={`${e.url}/commit/${r.commit_sha}`} target="_blank" rel="noreferrer"><code>{r.commit_sha.slice(0, 7)}</code></a></> : null} · {r.details.files_used ?? 0} files · {Math.round((r.duration_ms ?? 0) / 100) / 10}s</span>
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
            <tbody>{all.map((r) => <tr key={r.id}><td className="caption"><LocalTime iso={r.created_at} /></td><td>{CHECKS.find((c) => c.id === r.check_id)?.title.split(" (")[0] ?? r.check_id}</td>
              <td><span className={`pill pill-sm ${CLS[r.verdict] ?? ""}`}>{r.verdict}</span></td><td className="ink-2">{r.summary}</td><td><code>{r.commit_sha?.slice(0, 7) ?? "—"}</code></td></tr>)}</tbody></table></div>
        </section>)}
    </>
  );
}
