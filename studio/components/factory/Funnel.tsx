import { skillTitle } from "@/lib/names";
import Link from "next/link";
import { GATE_LABEL, GATE_HELP, GATE_ORDER, type Gate, type ClosestRow } from "@/lib/factory/funnel";
import { GatePill } from "./Pills";

const CLS: Record<Gate, string> = { ready: "pill-sage", needs_approval: "pill-hold", below_bar: "pill-rust", needs_eval: "pill-hold", draft: "", published: "pill-ink" };

/** Where every workspace skill stands on the way to being published — each count links to that list. */
export function FunnelStrip({ items, active }: { items: { gate: Gate }[]; active?: Gate | null }) {
  const n = (g: Gate) => items.filter((i) => i.gate === g).length;
  return (
    <div className="funnel" role="list" aria-label="Publishing funnel">
      {GATE_ORDER.map((g) => (
        <Link key={g} role="listitem" href={active === g ? "/pipeline" : `/pipeline?gate=${g}`} className={`funnel-step${active === g ? " is-on" : ""}`} title={GATE_HELP[g]}>
          <b>{n(g)}</b><span className={`pill pill-sm ${CLS[g]}`}>{GATE_LABEL[g]}</span>
        </Link>))}
    </div>
  );
}

/** "Ready to publish" queue: the skills one click from going live, with the next one to act on. */
export function ReadyQueue({ items }: { items: { slug: string; name: string; gate: Gate; version: number | null }[] }) {
  const ready = items.filter((i) => i.gate === "ready"), approve = items.filter((i) => i.gate === "needs_approval");
  if (!ready.length && !approve.length) return null;
  return (
    <section className="card card-pad mb-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="h3" style={{ margin: 0 }}>Ready to publish <span className="pill pill-sm pill-sage">{ready.length}</span>{approve.length > 0 && <> · waiting for approval <span className="pill pill-sm pill-hold">{approve.length}</span></>}</div>
        <Link className="link" href="/pipeline?gate=ready">Publish pipeline</Link>
      </div>
      <p className="caption">Published skills become tools on your MCP server and API. These have passed their evaluation gate.</p>
      <ul className="ini-repos">{[...ready, ...approve].slice(0, 6).map((i) => (
        <li key={i.slug}><Link className="link" href={`/skills/${i.slug}/release`}>{skillTitle(i.name)}{i.version ? ` v${i.version}` : ""}</Link> <span className="caption">— {i.gate === "ready" ? "publish" : "approve, then publish"}</span></li>))}</ul>
    </section>
  );
}

/** The skills nearest release, each with the one thing it is missing and a link to where that happens. */
export function ClosestList({ rows }: { rows: ClosestRow[] }) {
  if (!rows.length) return null;
  return (
    <section className="card card-pad mb-6">
      <div className="h3" style={{ marginTop: 0 }}>Closest to publishable</div>
      <p className="caption">Ranked by what stands between each skill and release: stage first, then the smallest gap to the required pass rate.</p>
      <ol className="closest">{rows.map((r) => (
        <li key={r.slug}><Link className="link" href={`/skills/${r.slug}/${r.tab}`}>{r.name}{r.version ? ` v${r.version}` : ""}</Link> <GatePill gate={r.gate} small /> <span className="caption">needs {r.missing}</span></li>))}</ol>
    </section>
  );
}
