"use client";
/* Advances a running agent one step per request until it stops (done, blocked, failed, or waiting for approval),
 * refreshing the server-rendered trace after each step. Approvals are recorded by reviewers/admins. */
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

export function AgentRunDriver({ runId, status, autoStart, canApprove, approvalRole }: { runId: string; status: string; autoStart: boolean; canApprove: boolean; approvalRole: string | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const started = useRef(false);

  const drive = async () => {
    setBusy(true); setErr(null);
    try {
      for (let i = 0; i < 60; i++) {
        const res = await fetch(`/api/agent-runs/${runId}/step`, { method: "POST" });
        const j = await res.json();
        router.refresh();
        if (!res.ok) { setErr(j.error?.message ?? `HTTP ${res.status}`); break; }
        if (j.status !== "running") break;
      }
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => { if (autoStart && status === "running" && !started.current) { started.current = true; void drive(); } }, [autoStart, status]); // eslint-disable-line react-hooks/exhaustive-deps

  const approve = async () => {
    setBusy(true); setErr(null);
    const res = await fetch(`/api/agent-runs/${runId}/approve`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ note }) });
    const j = await res.json();
    if (!res.ok) { setErr(j.error?.message ?? `HTTP ${res.status}`); setBusy(false); return; }
    router.refresh();
    await drive();
  };

  return (
    <div className="stack-sm">
      {status === "running" && <div className="action-row" style={{ marginTop: 0 }}><button type="button" className="btn btn-primary" onClick={drive} disabled={busy}>{busy ? "Running steps…" : "Continue run"}</button>{busy && <span className="caption">Each step runs on the server and is checked before the next starts.</span>}</div>}
      {status === "awaiting_approval" && (
        <div className="card card-pad stack-sm">
          <div className="h3">Waiting for approval{approvalRole ? ` · ${approvalRole}` : ""}</div>
          {canApprove ? (<>
            <textarea className="textarea" style={{ minHeight: 60 }} placeholder="What you checked (recorded with your approval)" value={note} onChange={(e) => setNote(e.target.value)} />
            <div className="action-row" style={{ marginTop: 0 }}><button type="button" className="btn btn-primary" onClick={approve} disabled={busy}>{busy ? "Working…" : "Approve and continue"}</button></div>
          </>) : <p className="caption">A reviewer or admin approves this step.</p>}
        </div>
      )}
      {err && <div className="notice notice-err" role="alert">{err}</div>}
    </div>
  );
}
