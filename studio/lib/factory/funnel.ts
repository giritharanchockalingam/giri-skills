/* The publishing funnel: where each workspace skill stands on the way to being published (and so to being an MCP/API
 * tool), read from the release gates — never estimated. Pure. */
export type Gate = "published" | "ready" | "needs_approval" | "below_bar" | "needs_eval" | "draft";
export const GATE_LABEL: Record<Gate, string> = {
  published: "Published", ready: "Ready to publish", needs_approval: "Needs approval", below_bar: "Below the bar", needs_eval: "Needs evaluation", draft: "Draft",
};
export const GATE_HELP: Record<Gate, string> = {
  published: "Live: exposed over MCP and the API.",
  ready: "Every release gate is met — one click to publish.",
  needs_approval: "Evaluation passes; a reviewer must approve this exact version.",
  below_bar: "Evaluated on the current cases, but the pass rate is under the release bar.",
  needs_eval: "Has test cases but no evaluation on the current set yet (or the cases changed since).",
  draft: "No test cases yet.",
};
export const GATE_ORDER: Gate[] = ["ready", "needs_approval", "below_bar", "needs_eval", "draft", "published"];

export interface GateInput { status: string | null; publishable: boolean | null; eval_gate_met: boolean | null; eval_current: boolean | null; latest_eval_run_id: string | null; eval_case_count: number; approval_valid: boolean | null; require_approval: boolean }

/** `working` = the latest draft/in-review/approved version's state (null when there is none); `hasPublished` = some version is live. */
export function gateOf(working: GateInput | null, hasPublished: boolean): Gate {
  if (!working) return hasPublished ? "published" : "draft";
  if (working.publishable) return "ready";
  if (working.eval_gate_met) return working.require_approval && !working.approval_valid ? "needs_approval" : "ready";
  if (!working.eval_case_count) return "draft";
  if (!working.latest_eval_run_id || !working.eval_current) return "needs_eval";
  return "below_bar";
}
