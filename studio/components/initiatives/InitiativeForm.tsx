"use client";
import { useActionState } from "react";
import { createInitiative, type InitiativeResult } from "@/app/initiatives/actions";

/** "Get <repositories> to <level> by <date>, owned by <person/team>" */
export function InitiativeForm({ repos, today }: { repos: string[]; today: string }) {
  const [state, action, pending] = useActionState<InitiativeResult, FormData>(createInitiative, null);
  return (
    <form action={action} className="auto-form">
      <div className="field"><label htmlFor="i-title">Goal</label><input id="i-title" name="title" className="input" required maxLength={140} placeholder="e.g. Every production app at Silver" /></div>
      <div className="form-grid form-grid-2">
        <div className="field"><label htmlFor="i-level">Target level</label>
          <select id="i-level" name="target_level" className="select" defaultValue="silver">
            <option value="bronze">Bronze — every check that applies has run</option>
            <option value="silver">Silver — no check fails</option>
            <option value="gold">Gold — every check passes</option>
          </select></div>
        <div className="field"><label htmlFor="i-due">Deadline</label><input id="i-due" name="due_on" type="date" className="input" required min={today} /></div>
      </div>
      <div className="field"><label htmlFor="i-owner">Owner</label><input id="i-owner" name="owner" className="input" required maxLength={120} placeholder="The accountable person or team" /></div>
      <fieldset className="field auto-set"><legend>Repositories (none ticked = every repository a check applies to)</legend>
        {repos.length === 0 ? <span className="caption">No repositories yet — connect GitHub in the Catalog.</span>
          : repos.map((r) => <label key={r} className="auto-opt"><input type="checkbox" name="repos" value={r} /> {r}</label>)}
      </fieldset>
      <div className="field"><label htmlFor="i-desc">Why (optional)</label><textarea id="i-desc" name="description" className="input" rows={2} maxLength={2000} /></div>
      <div className="flex items-center gap-3"><button className="btn btn-primary btn-sm" type="submit" disabled={pending}>{pending ? "Saving…" : "Start initiative"}</button>
        {state && <span role="status" className={`caption${state.ok ? "" : " ink-rust"}`}>{state.message}</span>}</div>
    </form>
  );
}
