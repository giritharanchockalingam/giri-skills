import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { loadActivity } from "@/lib/insights/load";
import { computeInsights, CHANNEL_LABEL } from "@/lib/insights/compute";
import { BaselineForm } from "@/components/insights/BaselineForm";
import { removeBaseline } from "@/app/insightsActions";
import { loadDelivery } from "@/lib/db/delivery";
import { collapseNotes } from "@/lib/insights/notes";
import { DeliveryTable } from "@/components/insights/DeliveryTable";
import { RefreshDelivery } from "@/components/insights/RefreshDelivery";
import { humanName } from "@/lib/names";
import { CHECKS } from "@/lib/scorecards/checks";
import { skills as repoSkills } from "@/lib/data";

export const metadata = { title: "Insights · Skills Factory" };
export const dynamic = "force-dynamic";

const PERIODS = [7, 30, 90] as const;
const nameOf = (id: string) => (id.startsWith("workspace/") ? `${id.slice(10)} (workspace)` : humanName(id.split("/")[1] ?? id));
const usd = (n: number) => n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: n < 10 ? 2 : 0 });
const pct = (n: number | null) => (n == null ? "—" : `${Math.round(n * 100)}%`);

/** Adoption, quality, spend and ROI from what this workspace actually ran. Nothing estimated without a stated basis. */
export default async function InsightsPage({ searchParams }: { searchParams: Promise<{ days?: string; skill?: string }> }) {
  const sp = await searchParams;
  const days = (PERIODS as readonly number[]).includes(Number(sp.days)) ? Number(sp.days) : 30;
  const ctx = await requireWorkspace();
  const since = new Date(Date.now() - days * 86_400_000).toISOString();
  const { acts, baselines, scores, truncated } = await loadActivity(ctx.supabase, ctx.workspace.id, since);
  const ins = computeInsights(acts, baselines, scores, days);
  // a baseline whose owner or source says "estimate" is not a measurement: the headline says so
  const estimated = baselines.filter((b) => /estimat/i.test(`${b.owner} ${b.source}`)).length;
  const delivery = await loadDelivery(ctx.supabase, ctx.workspace.id);
  const dWin: 30 | 90 = days === 90 ? 90 : 30;
  const notes = collapseNotes(delivery.flatMap((r) => r.notes));
  const admin = ctx.role === "admin";
  const maxWeek = Math.max(1, ...ins.weeks.map((w) => w.runs));
  const maxChan = Math.max(1, ...ins.channels.map((c) => c.runs));
  const library = (repoSkills as unknown as { id: string }[]).map((s) => ({ id: s.id, name: nameOf(s.id) })).sort((a, b) => a.name.localeCompare(b.name));

  return (
    <>
      <PageHead eyebrow="Govern · Insights" title="What skills" em="delivered" after="."
        lead="Who used skills, how often they succeeded, what they cost and the time they saved, from what this workspace actually ran. Hours saved use your own baselines: no baseline, no number." />
      <nav className="flex flex-wrap gap-2 mb-4" aria-label="Period">
        {PERIODS.map((d) => <Link key={d} href={`/insights?days=${d}`} className={`chip${d === days ? " chip-on" : ""}`} aria-current={d === days ? "page" : undefined}>Last {d} days</Link>)}
      </nav>

      <div className="cat-tiles mb-6">
        <div className="cat-tile"><b>{ins.total}</b><span title="Every run in this period: server (portal, API, MCP, playbook steps) and in the browser">runs (server + browser)</span></div>
        <div className="cat-tile"><b>{pct(ins.successRate)}</b><span>succeeded ({ins.ok} of {ins.total} runs, server + browser)</span></div>
        <div className="cat-tile"><b>{ins.people}</b><span>people and keys</span></div>
        <div className={`cat-tile${estimated ? " cat-tile-est" : ""}`}><b>{ins.roi.skillsWithBaseline ? ins.roi.hours : "—"}</b><span>{ins.roi.skillsWithBaseline ? <>hours saved{estimated ? <> — <b>estimated</b>: {estimated} of {ins.roi.skillsWithBaseline} baselines are estimates, not timed</> : ` (${ins.roi.skillsWithBaseline} measured baseline${ins.roi.skillsWithBaseline === 1 ? "" : "s"})`}</> : "hours saved: set a baseline below"}</span></div>
        {ins.roi.value != null && <div className="cat-tile"><b>{usd(ins.roi.value)}</b><span>value at your rates</span></div>}
        <div className="cat-tile"><b>{usd(ins.spend.usd)}</b><span>LLM spend ({ins.spend.runsWithCost} costed run{ins.spend.runsWithCost === 1 ? "" : "s"})</span></div>
      </div>

      <section className="card mb-6" id="delivery">
        <div className="card-pad" style={{ paddingBottom: 0 }}>
          <div className="flex flex-wrap items-center justify-between gap-2"><div className="h3" style={{ margin: 0 }}>Delivery (DORA) — last {dWin} days</div>
            {(ctx.role === "admin" || ctx.role === "author") && <RefreshDelivery />}</div>
          <p className="caption">From GitHub, per repository. Deploys: production deployments GitHub recorded, else merges to the default branch. Lead time: pull request opened → merged (approximates DORA&apos;s commit → production). Change failure: share of merges that revert or hotfix (a proxy; no incident data). Bands: DORA 2024 clusters for deploy frequency and lead time; none for change failure (2024&apos;s bands are not ordered).</p>
          {notes.map((n) => <p key={n} className="caption">ⓘ {n}</p>)}
        </div>
        <div className="card-pad">{delivery.length ? <DeliveryTable rows={delivery} window={dWin} /> : <p className="none" style={{ margin: 0 }}>Not measured yet — refresh, or sync the catalog.</p>}</div>
      </section>

      <div className="ins-grid mb-6">
        <section className="card card-pad">
          <div className="h3" style={{ marginTop: 0 }}>Runs per week</div>
          <div className="ins-cols" role="img" aria-label={`Runs per week: ${ins.weeks.map((w) => `${w.start} ${w.runs}`).join(", ")}`}>
            {ins.weeks.map((w) => (
              <div key={w.start} className="ins-col" title={`Week of ${w.start}: ${w.runs} run${w.runs === 1 ? "" : "s"}`}>
                <span className="ins-col-v">{w.runs || ""}</span>
                <span className="ins-col-bar" style={{ height: `${Math.max(w.runs ? 4 : 0, (w.runs / maxWeek) * 120)}px` }} />
                <span className="ins-col-x">{w.start.slice(5)}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="card card-pad">
          <div className="h3" style={{ marginTop: 0 }}>Where runs came from</div>
          <div className="tablewrap"><table className="ins-bars"><tbody>
            {ins.channels.map((c) => (
              <tr key={c.channel} title={`${CHANNEL_LABEL[c.channel]}: ${c.runs}`}>
                <th scope="row">{CHANNEL_LABEL[c.channel]}</th>
                <td><span className="ins-bar" style={{ width: `${(c.runs / maxChan) * 100}%` }} /></td>
                <td className="ins-n">{c.runs}</td>
              </tr>))}
          </tbody></table></div>
        </section>
      </div>

      <section className="card mb-6">
        <div className="card-pad" style={{ paddingBottom: 0 }}>
          <div className="h3" style={{ marginTop: 0 }}>Return on each skill</div>
          <p className="caption">A run counts as work when it succeeded, was not on sample inputs (the shipped samples, which are labelled fictional) and was not an evaluation. Hours = counted runs × your baseline minutes.</p>
        </div>
        <div className="tablewrap"><table className="mini">
          <thead><tr><th>Skill</th><th>Runs</th><th>Counted as work</th><th>Baseline (by hand)</th><th>Hours saved</th><th>Value</th>{admin && <th>Actions</th>}</tr></thead>
          <tbody>{ins.skills.length === 0 ? <tr><td colSpan={7} className="none">No runs in this period.</td></tr> : ins.skills.map((s) => (
            <tr key={s.skill}>
              <td>{s.skill.startsWith("workspace/") ? nameOf(s.skill) : <Link className="link" href={`/repo/${s.skill}`}>{nameOf(s.skill)}</Link>}</td>
              <td>{s.runs}</td><td>{s.counted}</td>
              <td>{s.baseline ? <>{s.baseline.manual_minutes} min{s.baseline.hourly_rate_usd != null ? ` · ${usd(s.baseline.hourly_rate_usd)}/h` : ""}<div className="caption">{s.baseline.owner} — {s.baseline.source}</div></>
                : <span className="caption">not set{admin && !s.skill.startsWith("workspace/") ? <> · <Link className="link" href={`/insights?days=${days}&skill=${encodeURIComponent(s.skill)}#baseline`}>set</Link></> : ""}</span>}</td>
              <td>{s.hours ?? "—"}</td><td>{s.value != null ? usd(s.value) : "—"}</td>
              {admin && <td>{s.baseline && <form action={removeBaseline}><input type="hidden" name="skill" value={s.skill} /><button className="link caption" type="submit">remove</button></form>}</td>}
            </tr>))}</tbody>
        </table></div>
        {admin && (
          <div className="card-pad" id="baseline">
            <div className="h3" style={{ marginTop: 0 }}>Set a baseline</div>
            <p className="caption">How long the task takes a person without the skill. Name who stands behind it and how it was measured — it is shown wherever the number is used, and every change is audited.</p>
            <BaselineForm skills={library} preset={sp.skill && library.some((l) => l.id === sp.skill) ? sp.skill : undefined} />
          </div>)}
      </section>

      <section className="card mb-6">
        <div className="card-pad" style={{ paddingBottom: 0 }}><div className="h3" style={{ marginTop: 0 }}>Scorecards across the catalog</div></div>
        <div className="tablewrap"><table className="mini">
          <thead><tr><th>Check</th><th>Pass</th><th>Warn</th><th>Fail</th><th>Error</th></tr></thead>
          <tbody>{ins.scorecards.byCheck.length === 0 ? <tr><td colSpan={5} className="none">No scorecards yet — run them from the <Link className="link" href="/catalog">Catalog</Link>.</td></tr>
            : ins.scorecards.byCheck.map((c) => (
              <tr key={c.check}><td><Link className="link" href="/catalog">{CHECKS.find((x) => x.id === c.check)?.title ?? c.check}</Link></td><td>{c.pass}</td><td>{c.warn}</td><td>{c.fail}</td><td>{c.error}</td></tr>))}</tbody>
        </table></div>
      </section>

      <p className="caption">Counted: runs in the portal, through the API and MCP, playbook steps, scorecard checks, evaluations, and skills run in the browser (recorded without their inputs since 19 Oct 2026). Spend is the cost the model provider reported, an estimate where marked.{truncated ? " Showing the most recent 5,000 records per source." : ""}</p>
    </>
  );
}
