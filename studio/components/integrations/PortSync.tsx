"use client";
import { useActionState } from "react";
import { syncToPort, type SyncState } from "@/app/integrations/actions";

export function PortSync({ disabled }: { disabled?: boolean }) {
  const [state, action, pending] = useActionState<SyncState | null, FormData>(syncToPort, null);
  return (
    <form action={action} className="stack-sm">
      <div><button className="btn btn-secondary btn-sm" type="submit" disabled={pending || disabled}>{pending ? "Pushing…" : "Push skills to Port"}</button></div>
      {state && <p role="status" className={`caption${state.ok ? "" : " ink-rust"}`} style={{ margin: 0 }}>{state.message}</p>}
      {state?.problems.length ? <details className="caption"><summary>{state.problems.length} problem{state.problems.length === 1 ? "" : "s"}</summary><ul>{state.problems.map((p) => <li key={p}>{p}</li>)}</ul></details> : null}
    </form>
  );
}
