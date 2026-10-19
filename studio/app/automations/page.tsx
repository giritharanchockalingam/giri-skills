import { LocalTime } from "@/components/LocalTime";
import Link from "next/link";
import { headers } from "next/headers";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { loadAutomations } from "@/lib/db/automations";
import { AutomationForm } from "@/components/automations/AutomationForm";
import { toggleAutomation, removeAutomation } from "./actions";
import { CHECKS } from "@/lib/scorecards/checks";
import { githubConfig, appInfo } from "@/lib/github/app";
import { adminConfigured, ADMIN_FIX } from "@/lib/supabase/server-admin";

export const metadata = { title: "Automations · Skills Factory" };
export const dynamic = "force-dynamic";

const CLS: Record<string, string> = { pass: "pill-sage", warn: "pill-hold", fail: "pill-rust", error: "pill-rust", skipped: "" };
const titleOf = (id: string) => CHECKS.find((c) => c.id === id)?.title.split(" (")[0] ?? id;

/** Workflow orchestrator: when something happens in GitHub, run checks and report back — with every run recorded. */
export default async function AutomationsPage() {
  const ctx = await requireWorkspace();
  const admin = ctx.role === "admin";
  const { automations, runs, repos } = await loadAutomations(ctx.supabase, ctx.workspace.id);
  const h = await headers();
  const origin = `${h.get("x-forwarded-proto") ?? "https"}://${h.get("x-forwarded-host") ?? h.get("host")}`;

  // setup: what the deployment and the GitHub App must allow for events to arrive and results to be posted
  const gh = githubConfig();
  let app: { permissions: Record<string, string>; events: string[] } | null = null, appErr: string | null = null;
  if (gh.ok) { try { app = await appInfo(gh.cfg); } catch (e) { appErr = (e as Error).message; } }
  const setup = [
    { ok: gh.ok, what: "GitHub App connected", fix: "Catalog → set up the GitHub App" },
    { ok: Boolean(process.env.GITHUB_WEBHOOK_SECRET), what: "Webhook secret set on the server", fix: "Vercel env GITHUB_WEBHOOK_SECRET = the App's webhook secret" },
    { ok: adminConfigured(), what: "Server can record runs without a user session", fix: ADMIN_FIX },
    { ok: app?.permissions.checks === "write", what: "App may post checks (Checks: read & write)", fix: "GitHub App settings → Permissions → Checks: Read and write" },
    { ok: !!app?.permissions.pull_requests, what: "App may read pull requests", fix: "GitHub App settings → Permissions → Pull requests: Read-only" },
    { ok: !!app && ["pull_request", "push"].every((e) => app!.events.includes(e)), what: "App receives pull_request and push events", fix: `GitHub App settings → Webhook: Active, URL ${origin}/api/github/webhook; Subscribe to events: Pull request, Push` },
  ];
  const ready = setup.every((s) => s.ok);

  return (
    <>
      <PageHead eyebrow="Workflow orchestrator" title="When something" em="happens" after=", act."
        lead="Automations run your scorecard checks on every pull request or change to the default branch, and report the verdict back on GitHub. Every run is recorded here." />

      <section className="card card-pad mb-6">
        <div className="flex flex-wrap items-center justify-between gap-2"><div className="h3" style={{ margin: 0 }}>Setup</div>
          <span className={`pill pill-sm ${ready ? "pill-sage" : "pill-hold"}`}>{ready ? "ready" : `${setup.filter((s) => !s.ok).length} step(s) left`}</span></div>
        {appErr && <p className="caption ink-rust">Could not read the GitHub App: {appErr}</p>}
        <ul className="auto-setup">{setup.map((s) => (
          <li key={s.what}><span aria-hidden="true">{s.ok ? "✅" : "⬜"}</span> {s.what}{!s.ok && <div className="caption">{s.fix}</div>}</li>))}</ul>
        {!ready && <p className="caption">After changing the App&apos;s permissions, GitHub asks the installation owner to accept them (Settings → Applications → the App → Review request).</p>}
      </section>

      <section className="card mb-6">
        <div className="card-pad" style={{ paddingBottom: 0 }}><div className="h3" style={{ marginTop: 0 }}>Automations</div></div>
        <div className="card-pad auto-table"><div className="tablewrap"><table className="mini">
          <thead><tr><th>Name</th><th>When</th><th>In</th><th>Run</th><th>Report</th><th>State</th>{admin && <th />}</tr></thead>
          <tbody>{automations.length === 0 ? <tr><td colSpan={7} className="none">No automations yet.</td></tr> : automations.map((a) => (
            <tr key={a.id}>
              <td><b>{a.name}</b></td>
              <td>{a.trigger === "github.pull_request" ? "pull request opened or updated" : "default branch changes"}</td>
              <td className="caption">{a.repos.length ? a.repos.join(", ") : "every repository"}</td>
              <td className="caption">{a.checks.length ? a.checks.map(titleOf).join(", ") : "every applicable check"}</td>
              <td className="caption">{a.report_to_github ? "check on GitHub" : "here only"}</td>
              <td><span className={`pill pill-sm ${a.enabled ? "pill-sage" : ""}`}>{a.enabled ? "on" : "off"}</span></td>
              {admin && <td className="flex gap-2">
                <form action={toggleAutomation}><input type="hidden" name="id" value={a.id} /><input type="hidden" name="enabled" value={String(!a.enabled)} /><button className="link caption" type="submit">{a.enabled ? "Turn off" : "Turn on"}</button></form>
                <form action={removeAutomation}><input type="hidden" name="id" value={a.id} /><button className="link caption" type="submit">Delete</button></form></td>}
            </tr>))}</tbody>
        </table></div></div>
        {admin && <div className="card-pad"><div className="h3" style={{ marginTop: 0 }}>New automation</div><AutomationForm repos={repos} checks={CHECKS.map((c) => ({ id: c.id, title: c.title }))} /></div>}
      </section>

      <section className="card">
        <div className="card-pad" style={{ paddingBottom: 0 }}><div className="h3" style={{ marginTop: 0 }}>Runs</div></div>
        <div className="card-pad auto-table"><div className="tablewrap"><table className="mini">
          <thead><tr><th>When</th><th>Automation</th><th>Repository</th><th>Event</th><th>Verdicts</th><th>On GitHub</th></tr></thead>
          <tbody>{runs.length === 0 ? <tr><td colSpan={6} className="none">No runs yet — they appear when GitHub sends an event.</td></tr> : runs.map((r) => (
            <tr key={r.id}>
              <td className="caption"><LocalTime iso={r.started_at} /></td>
              <td>{automations.find((a) => a.id === r.automation_id)?.name ?? "—"}</td>
              <td>{r.entity_id ? <Link className="link" href={`/catalog/${r.entity_id}`}>{r.repo}</Link> : r.repo}</td>
              <td className="caption">{r.event === "pull_request" ? `PR #${r.pr_number}` : "default branch"} · <code>{r.head_sha?.slice(0, 7)}</code></td>
              <td>{r.status === "running" ? <span className="caption">running…</span> : r.error ? <span className="caption ink-rust">{r.error}</span>
                : Object.entries(r.verdicts).map(([k, v]) => <span key={k} className={`pill pill-sm ${CLS[v.verdict] ?? ""}`} title={v.summary} style={{ marginRight: 4 }}>{titleOf(k)}: {v.verdict}</span>)}</td>
              <td>{r.check_run_url ? <a className="link caption" href={r.check_run_url} target="_blank" rel="noreferrer">check</a> : <span className="caption">—</span>}</td>
            </tr>))}</tbody>
        </table></div></div>
      </section>
    </>
  );
}
