"use client";
/* "No template fits? Compose one." — picks a catalog repository and a request kind, composes a pipeline on the server
 * (lib/delivery/compose.ts: the role per ADLC stage, the role's skills whose `fits` match the repository's stack), shows
 * the stages and the decision table, and lets the person start a run with it. Nothing is stored until the run starts;
 * the start action re-composes from the same inputs (deterministic), so no pipeline JSON travels from the browser. */
import { useActionState, useState } from "react";
import { ActionForm } from "./ActionForm";
import { composeDelivery, startComposedDelivery, type ComposeActionResult } from "@/app/deliverActions";
import type { RepoOption } from "./DeliverForm";

export interface KindOption { id: string; description: string; mode: string; stages: string[] }

export function ComposeDelivery({ repos, kinds, githubConfigured }: { repos: RepoOption[]; kinds: KindOption[]; githubConfigured: boolean }) {
  const [state, formAction, pending] = useActionState(composeDelivery, null as ComposeActionResult | null);
  const [repo, setRepo] = useState("");
  const [kind, setKind] = useState(kinds[0]?.id ?? "");
  const [mode, setMode] = useState("");
  const [showAll, setShowAll] = useState(false);
  const k = kinds.find((x) => x.id === kind);
  const c = state?.composed;
  const rows = (c?.decisions ?? []).filter((d) => showAll || d.decision !== "rejected" || d.step !== "-");
  return (
    <div className="card card-pad stack-sm">
      <p className="caption">No template fits? Compose one. One stage per ADLC stage the request kind needs, owned by the role that lists it, running the role&apos;s skills whose <code>fits</code> match the repository&apos;s stack (from the catalog sync). Stages with no fitting skill are dropped and say so.</p>
      <form action={formAction} className="stack-sm">
        <div className="form-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
          <div className="field">
            <label htmlFor="cp-repo">Repository</label>
            <input id="cp-repo" name="repo" className="input" list="cp-repos" required placeholder="owner/name from the catalog" value={repo} onChange={(e) => setRepo(e.target.value)} />
            <datalist id="cp-repos">{repos.map((r) => <option key={r.key} value={r.key}>{r.title}</option>)}</datalist>
            <span className="hint">{repos.length ? "Its stack signals decide which skills fit." : "No repositories in the catalog yet: connect GitHub under Platform → Repositories."}</span>
          </div>
          <div className="field">
            <label htmlFor="cp-kind">Request kind</label>
            <select id="cp-kind" name="request_kind" className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
              {kinds.map((x) => <option key={x.id} value={x.id}>{x.id}</option>)}
            </select>
            {k && <span className="hint">{k.description} Stages: {k.stages.join(" → ")}.</span>}
          </div>
          <div className="field">
            <label htmlFor="cp-mode">Mode</label>
            <select id="cp-mode" name="mode" className="select" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="">Default for the kind ({k?.mode ?? "brownfield"})</option>
              <option value="brownfield">Brownfield — a change on an existing repository</option>
              <option value="greenfield">Greenfield — bootstrap first, profile read after</option>
            </select>
          </div>
        </div>
        <div className="action-row">
          <button type="submit" className="btn" disabled={pending || !kinds.length} aria-busy={pending}>{pending ? "Composing…" : "Compose"}</button>
          {state && <div className={`notice ${state.ok ? "notice-ok" : "notice-err"}`} role="status">{state.message}</div>}
        </div>
      </form>
      {c && (
        <div className="stack-sm">
          {c.stages.length > 0 && (
            <ul className="list-plain">
              {c.stages.map((s) => <li key={s.id}><b className="mono-sm">{s.id}</b> <span className="caption">({s.role})</span>: {s.steps.join(" → ")}</li>)}
            </ul>
          )}
          {c.notes.map((n) => <div key={n} className="notice notice-hold">{n}</div>)}
          <div className="caption">Stack: {c.stacks.length ? c.stacks.join(", ") : "no signals"} · <button type="button" className="link" onClick={() => setShowAll((v) => !v)}>{showAll ? "Hide" : "Show"} skills without a wiring recipe</button></div>
          <div className="tablewrap">
            <table className="tbl">
              <thead><tr><th>Stage</th><th>Role</th><th>Step</th><th>Skill</th><th>Decision</th><th>Why</th></tr></thead>
              <tbody>
                {rows.map((d, i) => (
                  <tr key={i}>
                    <td className="mono-sm">{d.stage}</td><td className="mono-sm">{d.role}</td><td className="mono-sm">{d.step}</td>
                    <td className="mono-sm">{d.skill ?? ""}</td><td>{d.decision}</td><td>{d.why}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {c.name && (
            <ActionForm action={startComposedDelivery} submit="Start delivery with this pipeline" className="stack-sm"
              hidden={{ repo, request_kind: c.request_kind, mode: c.mode }}>
              <div className="form-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                <div className="field">
                  <label htmlFor="cp-ref">Branch or commit</label>
                  <input id="cp-ref" name="ref" className="input" placeholder="default branch" />
                </div>
                <div className="field">
                  <label htmlFor="cp-executor">Runs on</label>
                  <select id="cp-executor" name="executor" className="select" defaultValue={githubConfigured ? "github-actions" : "ide"}>
                    <option value="github-actions">GitHub Actions (delivery.yml in the library){githubConfigured ? "" : " — not configured"}</option>
                    <option value="ide">My IDE (I run scripts/deliver.py and post evidence)</option>
                  </select>
                  <span className="hint">The executor reads the composed pipeline from the run (<code>pipeline_spec</code>); the command it prints works as printed.</span>
                </div>
              </div>
              <div className="field">
                <label htmlFor="cp-request">Request</label>
                <textarea id="cp-request" name="request" className="textarea" required minLength={4} placeholder="What should be delivered, in your own words. Acceptance criteria help." />
              </div>
            </ActionForm>
          )}
        </div>
      )}
    </div>
  );
}
