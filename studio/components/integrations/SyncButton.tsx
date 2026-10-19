"use client";
import { useActionState } from "react";
import { syncIntegration, type SyncState } from "@/app/integrations/actions";

export function IntegrationSync({ provider, disabled }: { provider: "vercel" | "supabase"; disabled?: boolean }) {
  const [state, action, pending] = useActionState<SyncState | null, FormData>(syncIntegration, null);
  return (
    <form action={action} className="stack-sm">
      <input type="hidden" name="provider" value={provider} />
      <div><button className="btn btn-secondary btn-sm" type="submit" disabled={pending || disabled}>{pending ? "Syncing…" : "Sync now"}</button></div>
      {state && <p role="status" className={`caption${state.ok ? "" : " ink-rust"}`} style={{ margin: 0 }}>{state.message}</p>}
      {state?.problems.length ? <details className="caption"><summary>{state.problems.length} note{state.problems.length === 1 ? "" : "s"}</summary><ul>{state.problems.map((p) => <li key={p}>{p}</li>)}</ul></details> : null}
    </form>
  );
}
