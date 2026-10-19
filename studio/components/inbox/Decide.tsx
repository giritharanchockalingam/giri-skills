"use client";
/* Approve (runs the action at once, as the approver) or reject, with an optional note. */
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

export function Decide({ id, mine, canDecide }: { id: string; mine: boolean; canDecide: boolean }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<null | "approve" | "reject">(null);
  const [out, setOut] = useState<{ ok: boolean; message: string; run_id?: string | null } | null>(null);
  if (mine) return <span className="caption">Your request — another reviewer or admin decides.</span>;
  if (!canDecide) return <span className="caption">A reviewer or admin decides.</span>;
  async function go(approve: boolean) {
    setBusy(approve ? "approve" : "reject"); setOut(null);
    try {
      const r = await fetch(`/api/actions/${id}/decide`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approve, note }) });
      const j = await r.json();
      setOut(r.ok ? j : { ok: false, message: j?.error?.message ?? `HTTP ${r.status}` });
      if (r.ok) router.refresh();
    } catch (e) { setOut({ ok: false, message: String(e) }); }
    setBusy(null);
  }
  return (
    <div className="decide">
      <input className="input" placeholder="Note (optional)" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} aria-label="Decision note" />
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-primary btn-sm" disabled={!!busy} onClick={() => go(true)}>{busy === "approve" ? "Approving and running…" : "Approve and run"}</button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={!!busy} onClick={() => go(false)}>{busy === "reject" ? "Rejecting…" : "Reject"}</button>
      </div>
      {out && <p role="status" className={`caption${out.ok ? "" : " ink-rust"}`}>{out.message} {out.run_id && <Link className="link" href={`/runs/${out.run_id}`}>Open the run</Link>}</p>}
    </div>
  );
}
