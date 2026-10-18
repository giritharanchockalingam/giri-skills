"use client";
/* Admin check of the Python runtime: calls /api/runtime/health (server → function with the shared secret). */
import { useState } from "react";

export function RuntimeStatus() {
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const check = async () => {
    setBusy(true);
    try {
      const r = await fetch("/api/runtime/health", { cache: "no-store" });
      const j = await r.json();
      if (!r.ok) setState({ ok: false, text: j.error?.message ?? `HTTP ${r.status}` });
      else if (j.ok) setState({ ok: true, text: `Reachable at ${j.url} — Python ${j.detail?.python}, ${j.detail?.bundle_files} bundle files, ANTHROPIC_API_KEY ${j.detail?.anthropic_key_present ? "present" : "absent"} in the function, max deadline ${j.detail?.max_timeout_s}s.` });
      else setState({ ok: false, text: j.error ?? "unavailable" });
    } catch (e) { setState({ ok: false, text: (e as Error).message }); }
    finally { setBusy(false); }
  };
  return (
    <span>
      <button type="button" className="btn btn-secondary btn-sm" onClick={check} disabled={busy}>{busy ? "Checking…" : "Check runtime"}</button>
      {state && <div className={`notice mt-2 ${state.ok ? "notice-ok" : "notice-err"}`} role="status">{state.text}</div>}
    </span>
  );
}
