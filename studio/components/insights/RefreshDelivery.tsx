"use client";
import { useActionState } from "react";
import { refreshDeliveryNow, type BaselineResult } from "@/app/insightsActions";

/** Recompute delivery metrics from GitHub now (authors and admins). */
export function RefreshDelivery() {
  const [state, action, pending] = useActionState<BaselineResult | null>(async () => refreshDeliveryNow(), null);
  return (
    <form action={action} className="flex flex-wrap items-center gap-2">
      <button className="btn btn-secondary btn-sm" type="submit" disabled={pending}>{pending ? "Measuring…" : "Refresh from GitHub"}</button>
      {state && <span role="status" className={`caption${state.ok ? "" : " ink-rust"}`}>{state.message}</span>}
    </form>
  );
}
