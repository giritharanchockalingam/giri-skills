"use client";
/* "Run evaluation": starts an evaluation run, then steps through the cases one request at a time (each within
 * the runtime's deadline). Progress is persisted server-side after every case. */
import { useState } from "react";
import { useRouter } from "next/navigation";
import type { EvalCaseResult } from "@/lib/factory/db";

export function EvalRunner({ versionId, cases, disabled, reason }: { versionId: string; cases: number; disabled: boolean; reason: string | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number; last: EvalCaseResult | null } | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const run = async () => {
    setBusy(true); setMsg(null); setProgress(null);
    try {
      const start = await fetch("/api/eval-runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ version_id: versionId }) });
      const sj = await start.json();
      if (!start.ok) { setMsg({ ok: false, text: sj.error?.message ?? `HTTP ${start.status}` }); return; }
      const id = sj.eval_run_id as string;
      let done = 0;
      for (;;) {
        const r = await fetch(`/api/eval-runs/${id}/step`, { method: "POST" });
        const j = await r.json();
        if (!r.ok) { setMsg({ ok: false, text: j.error?.message ?? `HTTP ${r.status}` }); break; }
        done++;
        if (j.done) { setProgress({ done: sj.cases, total: sj.cases, last: null }); setMsg({ ok: true, text: `Evaluation finished: ${Math.round((j.pass_rate ?? 0) * 100)}% of cases passed. Results are recorded against this version and case set.` }); break; }
        setProgress({ done, total: sj.cases, last: j.last });
      }
      router.refresh();
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    finally { setBusy(false); }
  };
  return (
    <div>
      <div className="action-row" style={{ marginTop: 0 }}>
        <button type="button" className="btn btn-primary" disabled={busy || disabled} onClick={run}>{busy ? `Running case ${Math.min((progress?.done ?? 0) + 1, cases)} of ${cases}…` : `Run evaluation (${cases} case${cases === 1 ? "" : "s"})`}</button>
        {reason && <span className="caption">{reason}</span>}
      </div>
      {busy && progress && <div className="run-bar mt-3"><span style={{ width: `${(progress.done / progress.total) * 100}%` }} /></div>}
      {progress?.last && busy && <p className="caption mt-2">Last: {progress.last.name} — {progress.last.status}, {progress.last.passed}/{progress.last.total} checks</p>}
      <div role="status" aria-live="polite" className="mt-3">{msg && <div className={`notice ${msg.ok ? "notice-ok" : "notice-err"}`}>{msg.text}</div>}</div>
    </div>
  );
}
