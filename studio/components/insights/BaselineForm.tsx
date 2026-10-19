"use client";
import { useActionState } from "react";
import { saveBaseline } from "@/app/insightsActions";

/** Set the workspace's own manual-effort baseline for a skill (owner + how it was measured are required). */
export function BaselineForm({ skills, preset }: { skills: { id: string; name: string }[]; preset?: string }) {
  const [state, action, pending] = useActionState(saveBaseline, null);
  return (
    <form action={action} className="ins-form">
      <div className="field"><label htmlFor="b-skill">Skill</label>
        <select id="b-skill" name="skill" className="select" defaultValue={preset ?? ""} required>
          <option value="" disabled>Choose…</option>{skills.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select></div>
      <div className="field"><label htmlFor="b-min">Minutes by hand, per run</label><input id="b-min" name="manual_minutes" className="input" type="number" min={1} max={10000} step="0.5" required /></div>
      <div className="field"><label htmlFor="b-rate">Loaded hourly rate, USD (optional)</label><input id="b-rate" name="hourly_rate_usd" className="input" type="number" min={1} max={2000} step="0.01" /></div>
      <div className="field"><label htmlFor="b-owner">Owner</label><input id="b-owner" name="owner" className="input" required maxLength={120} placeholder="who stands behind the number" /></div>
      <div className="field ins-wide"><label htmlFor="b-src">How it was measured</label><input id="b-src" name="source" className="input" required minLength={3} maxLength={300} placeholder="e.g. timed 5 manual RLS reviews, Oct 2026" /></div>
      <div className="ins-wide flex items-center gap-3"><button className="btn btn-primary btn-sm" type="submit" disabled={pending}>{pending ? "Saving…" : "Save baseline"}</button>
        {state && <span role="status" className={`caption${state.ok ? "" : " ink-rust"}`}>{state.message}</span>}</div>
    </form>
  );
}
