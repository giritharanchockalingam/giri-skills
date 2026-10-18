"use client";
/* A form bound to a server action with inline feedback (role=status) and a pending state on its submit button.
 * Every mutation in the factory UI goes through this so feedback after an action is consistent. */
import { useActionState, useState, type ReactNode } from "react";
import type { ActionResult } from "@/app/actions";
import { KeyReveal } from "./KeyReveal";

type Act = (prev: ActionResult | null, fd: FormData) => Promise<ActionResult>;

export function ActionForm({ action, children, submit, submitClass = "btn btn-primary", confirm, className, hidden = {}, render, revealKey, disabled }: {
  action: Act; children?: ReactNode; submit: string; submitClass?: string; confirm?: string; className?: string; disabled?: boolean;
  hidden?: Record<string, string | number | undefined | null>;
  /** Extra content rendered from the result (e.g. a one-time API key). */
  render?: (r: ActionResult & Record<string, unknown>) => ReactNode;
  /** Server components cannot pass functions to this client component: set this to show a one-time `key` from the result. */
  revealKey?: boolean;
}) {
  const [state, formAction, pending] = useActionState(action, null);
  // Two-step confirm in the page (no native dialog: screen readers and automation can see it, and it never blocks the tab).
  const [armed, setArmed] = useState(false);
  return (
    <form action={formAction} className={className} onSubmit={(e) => { if (confirm && !armed) { e.preventDefault(); setArmed(true); } else setArmed(false); }}>
      {Object.entries(hidden).map(([k, v]) => v != null && <input key={k} type="hidden" name={k} value={String(v)} />)}
      {children}
      <div className="action-row">
        {confirm && armed ? (
          <>
            <span className="notice notice-hold" role="alert">{confirm}</span>
            <button type="submit" className={submitClass} disabled={pending} aria-busy={pending}>{pending ? "Working…" : "Confirm"}</button>
            <button type="button" className="btn" onClick={() => setArmed(false)}>Cancel</button>
          </>
        ) : (
          <button type="submit" className={submitClass} disabled={pending || disabled} aria-busy={pending}>{pending ? "Working…" : submit}</button>
        )}
        {state && <div className={`notice ${state.ok ? "notice-ok" : "notice-err"}`} role="status">{state.message}</div>}
      </div>
      {state && render?.(state as ActionResult & Record<string, unknown>)}
      {state && revealKey && typeof (state as ActionResult & Record<string, unknown>).key === "string" && <KeyReveal value={(state as ActionResult & Record<string, unknown>).key as string} />}
    </form>
  );
}
