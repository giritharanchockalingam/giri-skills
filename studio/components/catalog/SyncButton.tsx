"use client";
import { useState, useTransition } from "react";
import { syncNow } from "@/app/catalog/actions";

export function SyncButton() {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<{ ok: boolean; message: string; errors?: string[] } | null>(null);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" className="btn btn-secondary btn-sm" disabled={pending} aria-busy={pending} onClick={() => start(async () => setMsg(await syncNow()))}>
        {pending ? "Syncing…" : "Sync now"}
      </button>
      <span role="status" className={`caption${msg && !msg.ok ? " ink-rust" : ""}`}>{msg?.message}</span>
      {msg?.errors?.length ? <ul className="caption" style={{ width: "100%", margin: "4px 0 0 18px" }}>{msg.errors.map((e) => <li key={e}>{e}</li>)}</ul> : null}
    </div>
  );
}
