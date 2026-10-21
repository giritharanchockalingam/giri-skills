"use client";
/* "What do you need done?" — the library picks the skill for a plain-language task, says what you will get and who
 * owns that work, and links straight to running it (on its own example first, or on your files). */
import Link from "next/link";
import { humanName } from "@/lib/names";
import { useState, useTransition } from "react";
import { routeAnyTask, type AnyRouteHit } from "@/app/talentActions";

const human = humanName;
const tryHref = (id: string, task: string) => `/library/${id}/test?example=1&task=${encodeURIComponent(task.slice(0, 300))}`;
const ownHref = (id: string, task: string) => `/library/${id}/test?task=${encodeURIComponent(task.slice(0, 300))}`;

export function TaskBox({ suggestions }: { suggestions: string[] }) {
  const [task, setTask] = useState("");
  const [hits, setHits] = useState<AnyRouteHit[] | null>(null);
  const [msg, setMsg] = useState("");
  const [asked, setAsked] = useState("");
  const [pending, start] = useTransition();
  const go = (t: string) => {
    if (t.trim().length < 8) return;
    setAsked(t);
    start(async () => {
      const r = await routeAnyTask(t);
      setHits(r.ok ? r.hits ?? [] : []);
      setMsg(r.ok ? "" : r.message);
    });
  };
  return (
    <div className="card card-pad fd-task">
      <label htmlFor="fd-task" className="h3" style={{ display: "block" }}>Describe the work</label>
      <textarea id="fd-task" className="textarea fd-task-input" rows={3} value={task} onChange={(e) => setTask(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) go(task); }}
        placeholder="e.g. Check the row-level security in my Supabase migration before I merge" />
      <div className="action-row" style={{ marginTop: 10 }}>
        <button type="button" className="btn btn-primary" disabled={pending || task.trim().length < 8} title={task.trim().length < 8 ? "Describe the work first" : undefined} onClick={() => go(task)} aria-busy={pending} aria-describedby="fd-task-hint">
          {pending ? "Finding…" : "Find a skill for this"}
        </button>
        {task.trim().length < 8 && !pending && <span id="fd-task-hint" className="caption">{task.trim() ? `Say a little more (${8 - task.trim().length} more character${8 - task.trim().length === 1 ? "" : "s"})` : "Describe the work first"} · </span>}
        <span className="caption">or try:</span>
        {suggestions.map((s) => (
          <button key={s} type="button" className="chip fd-suggest" onClick={() => { setTask(s); go(s); }}>{s}</button>
        ))}
      </div>

      {msg && <p className="notice notice-err mt-3" role="status">{msg}</p>}
      {hits && hits.length > 0 && (
        <ol className="fd-hits" aria-label={`Skills for: ${asked}`}>
          {hits.map((h, i) => (
            <li key={h.skill} className={`fd-hit${i === 0 ? " fd-best" : ""}`}>
              <div className="fd-hit-head">
                <b>{human(h.name)}</b>
                {i === 0 ? <span className="pill pill-sm pill-sage">best match</span> : <span className="caption">also relevant</span>}
              </div>
              <p className="fd-get"><span className="caption">You get:</span> {h.youGet}</p>
              {h.owners.length > 0 && <p className="caption">Usually done by: {h.owners.join(" · ")}</p>}
              <div className="action-row" style={{ marginTop: 8 }}>
                {h.example && <Link href={tryHref(h.skill, asked)} className="btn btn-primary btn-sm" title="Run it on sample inputs">Try it on an example</Link>}
                <Link href={ownHref(h.skill, asked)} className="btn btn-secondary btn-sm" title="Run it on your inputs">Use my own files</Link>
                <span className="caption">matched: {h.matched.slice(0, 6).join(", ")}</span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
