"use client";
/* A form bound to a server action with inline feedback (role=status) and a pending state on its submit button.
 * Every mutation in the factory UI goes through this so feedback after an action is consistent. */
import { useActionState, type ReactNode } from "react";
import type { ActionResult } from "@/app/actions";

type Act = (prev: ActionResult | null, fd: FormData) => Promise<ActionResult>;

export function ActionForm({ action, children, submit, submitClass = "btn btn-primary", confirm, className, hidden = {}, render, disabled }: {
  action: Act; children?: ReactNode; submit: string; submitClass?: string; confirm?: string; className?: string; disabled?: boolean;
  hidden?: Record<string, string | number | undefined | null>;
  /** Extra content rendered from the result (e.g. a one-time API key). */
  render?: (r: ActionResult & Record<string, unknown>) => ReactNode;
}) {
  const [state, formAction, pending] = useActionState(action, null);
  return (
    <form action={formAction} className={className} onSubmit={(e) => { if (confirm && !window.confirm(confirm)) e.preventDefault(); }}>
      {Object.entries(hidden).map(([k, v]) => v != null && <input key={k} type="hidden" name={k} value={String(v)} />)}
      {children}
      <div className="action-row">
        <button type="submit" className={submitClass} disabled={pending || disabled} aria-busy={pending}>{pending ? "Working…" : submit}</button>
        {state && <div className={`notice ${state.ok ? "notice-ok" : "notice-err"}`} role="status">{state.message}</div>}
      </div>
      {state && render?.(state as ActionResult & Record<string, unknown>)}
    </form>
  );
}
