import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { loadCatalog } from "@/lib/db/catalog";
import { listInitiatives } from "@/lib/db/initiatives";
import { progressOf } from "@/lib/scorecards/initiatives";
import { LEVEL_LABEL, LEVEL_RULE } from "@/lib/scorecards/levels";
import { LevelBadge } from "@/components/catalog/LevelBadge";
import { InitiativeForm } from "@/components/initiatives/InitiativeForm";
import { changeInitiativeStatus, removeInitiative } from "./actions";

export const metadata = { title: "Initiatives · Skills Factory" };
export const dynamic = "force-dynamic";

const fmt = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { dateStyle: "medium", timeZone: "UTC" });

/** Initiatives: a scorecard level as a goal, with an owner and a deadline; progress is read from the live scorecard. */
export default async function InitiativesPage() {
  const ctx = await requireWorkspace();
  const canWrite = ctx.role === "admin" || ctx.role === "author";
  const [catalog, initiatives] = await Promise.all([loadCatalog(ctx.supabase, ctx.workspace.id), listInitiatives(ctx.supabase, ctx.workspace.id)]);
  const entities = catalog.entities.filter((e) => !e.archived);
  const latest = new Map<string, { check_id: string; verdict: string }[]>();
  for (const r of catalog.scores) latest.set(r.entity_id, [...(latest.get(r.entity_id) ?? []), r]);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <PageHead eyebrow="Catalog · initiatives" title="Raise the" em="bar" after=", on a date."
        lead="An initiative sets a scorecard level as the goal for some or all repositories, with an owner and a deadline. Progress is read from the live scorecard — it moves when the checks do." />
      <p className="caption mb-6"><Link className="link" href="/catalog">Catalog</Link> · levels: Bronze — {LEVEL_RULE.bronze} · Silver — {LEVEL_RULE.silver} · Gold — {LEVEL_RULE.gold}.</p>

      {initiatives.length === 0 && <section className="card card-pad mb-6"><p className="none" style={{ margin: 0 }}>No initiatives yet.{canWrite ? " Start one below." : ""}</p></section>}

      <div className="stack mb-6">
        {initiatives.map((ini) => {
          const p = progressOf(ini, entities, latest);
          const closed = ini.status === "closed";
          const state = closed ? "closed" : p.total > 0 && p.met === p.total ? "met" : p.overdue ? "overdue" : p.daysLeft <= 14 ? "due soon" : "on track";
          const pill = state === "met" ? "pill-sage" : state === "overdue" ? "pill-rust" : state === "due soon" ? "pill-hold" : "";
          return (
            <section key={ini.id} className={`card card-pad initiative${closed ? " is-closed" : ""}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="h3" style={{ margin: 0 }}>{ini.title}</div>
                  <div className="caption">Target <LevelBadge level={ini.target_level} /> · owner <b>{ini.owner}</b> · due {fmt(ini.due_on)}{!closed && (p.daysLeft >= 0 ? ` (${p.daysLeft} day${p.daysLeft === 1 ? "" : "s"} left)` : ` (${-p.daysLeft} day${p.daysLeft === -1 ? "" : "s"} late)`)}</div>
                </div>
                <span className={`pill pill-sm ${pill}`}>{state}</span>
              </div>
              {ini.description && <p className="ink-2" style={{ margin: "8px 0 0" }}>{ini.description}</p>}
              <div className="progress mt-3" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={p.pct} aria-label={`${p.met} of ${p.total} repositories at ${LEVEL_LABEL[ini.target_level]} or above`}>
                <span style={{ width: `${p.pct}%` }} />
              </div>
              <div className="caption mt-1">{p.met} of {p.total} repositor{p.total === 1 ? "y" : "ies"} at {LEVEL_LABEL[ini.target_level]} or above ({p.pct}%)</div>
              {p.total === 0 && <p className="caption">No repository is in scope: none has a check that applies{ini.repos.length ? " among those chosen" : ""}.</p>}
              <ul className="ini-repos">{p.repos.map((r) => (
                <li key={r.key}>
                  <span aria-hidden="true">{r.met ? "✅" : "⬜"}</span>{" "}
                  {r.id ? <Link className="link" href={`/catalog/${r.id}`}>{r.key}</Link> : <span>{r.key}</span>}{" "}
                  {r.result && <LevelBadge level={r.result.level} />}
                  {r.note && <span className="caption"> — {r.note}</span>}
                  {!r.met && r.result && r.result.level !== "n/a" && (() => {
                    const need = r.result.blockers.length && r.result.next === ini.target_level ? r.result.blockers : null;
                    return need ? <div className="caption">needs: {need.map((b) => `${b.title} ${b.reason}`).join("; ")}</div>
                      : <div className="caption">next: reach {LEVEL_LABEL[r.result.next ?? ini.target_level]} first ({r.result.blockers.map((b) => `${b.title} ${b.reason}`).join("; ")})</div>;
                  })()}
                </li>))}</ul>
              {canWrite && (
                <div className="flex flex-wrap gap-3 mt-2">
                  <form action={changeInitiativeStatus}><input type="hidden" name="id" value={ini.id} /><input type="hidden" name="status" value={closed ? "active" : "closed"} /><button className="link caption" type="submit">{closed ? "Reopen" : "Close"}</button></form>
                  {ctx.role === "admin" && <form action={removeInitiative}><input type="hidden" name="id" value={ini.id} /><button className="link caption" type="submit">Delete</button></form>}
                </div>)}
            </section>
          );
        })}
      </div>

      {canWrite && (
        <section className="card card-pad">
          <div className="h3" style={{ marginTop: 0 }}>New initiative</div>
          <InitiativeForm repos={entities.map((e) => e.key)} today={today} />
        </section>)}
    </>
  );
}
