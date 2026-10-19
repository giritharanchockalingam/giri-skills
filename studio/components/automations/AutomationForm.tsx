"use client";
import { useActionState } from "react";
import { createAutomation, type CreateResult } from "@/app/automations/actions";

/** "When <event> in <repositories> → run <checks> → report on GitHub" */
export function AutomationForm({ repos, checks }: { repos: string[]; checks: { id: string; title: string }[] }) {
  const [state, action, pending] = useActionState<CreateResult, FormData>(createAutomation, null);
  return (
    <form action={action} className="auto-form">
      <div className="field"><label htmlFor="a-name">Name</label><input id="a-name" name="name" className="input" required maxLength={120} placeholder="e.g. Pull request gate" /></div>
      <div className="field"><label htmlFor="a-trigger">When</label>
        <select id="a-trigger" name="trigger" className="select" defaultValue="github.pull_request">
          <option value="github.pull_request">a pull request is opened or updated</option>
          <option value="github.push">the default branch changes (keeps the scorecard current)</option>
        </select></div>
      <fieldset className="field auto-set"><legend>In (none ticked = every repository in the catalog)</legend>
        {repos.length === 0 ? <span className="caption">No repositories yet — connect GitHub in the Catalog.</span>
          : repos.map((r) => <label key={r} className="auto-opt"><input type="checkbox" name="repos" value={r} /> {r}</label>)}
      </fieldset>
      <fieldset className="field auto-set"><legend>Run (none ticked = every check that applies)</legend>
        {checks.map((c) => <label key={c.id} className="auto-opt"><input type="checkbox" name="checks" value={c.id} /> {c.title}</label>)}
      </fieldset>
      <label className="auto-opt"><input type="checkbox" name="report_to_github" defaultChecked /> Report the result on GitHub (a check on the commit or pull request)</label>
      <div className="flex items-center gap-3"><button className="btn btn-primary btn-sm" type="submit" disabled={pending}>{pending ? "Saving…" : "Create automation"}</button>
        {state && <span role="status" className={`caption${state.ok ? "" : " ink-rust"}`}>{state.message}</span>}</div>
    </form>
  );
}
