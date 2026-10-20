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

/** "Closest to publishable": every unpublished skill ranked by how little stands between it and release —
 *  funnel stage first, then (below the bar) the smallest gap to the required pass rate, then (needs evaluation) the most
 *  cases ready to run. Each row says exactly what is missing. Pure; read from the release gates, never estimated. */
export interface ClosestInput { slug: string; name: string; gate?: Gate; passRate: number | null; minPassRate: number | null; cases: number; version: number | null }
export interface ClosestRow { slug: string; name: string; gate: Gate; version: number | null; missing: string; tab: "release" | "evaluations" }
const pctTxt = (n: number) => `${Math.round(n * 100)}%`;
export function closestToPublish(items: ClosestInput[], limit = 5): ClosestRow[] {
  const rank: Gate[] = ["ready", "needs_approval", "below_bar", "needs_eval", "draft"];
  const gap = (i: ClosestInput) => (i.minPassRate ?? 0) - (i.passRate ?? 0);
  return items
    .filter((i): i is ClosestInput & { gate: Gate } => !!i.gate && i.gate !== "published")
    .sort((a, b) => rank.indexOf(a.gate) - rank.indexOf(b.gate)
      || (a.gate === "below_bar" ? gap(a) - gap(b) : 0)
      || (a.gate === "needs_eval" ? b.cases - a.cases : 0)
      || a.name.localeCompare(b.name))
    .slice(0, limit)
    .map((i) => ({
      slug: i.slug, name: i.name, gate: i.gate, version: i.version,
      tab: i.gate === "ready" || i.gate === "needs_approval" ? "release" : "evaluations",
      missing: i.gate === "ready" ? "nothing: publish it"
        : i.gate === "needs_approval" ? "a reviewer's approval"
        : i.gate === "below_bar" ? (i.passRate != null && i.minPassRate != null ? `${pctTxt(gap(i))} more pass rate (${pctTxt(i.passRate)} now, ${pctTxt(i.minPassRate)} required)` : "a higher pass rate")
        : i.gate === "needs_eval" ? `an evaluation run on its ${i.cases} case${i.cases === 1 ? "" : "s"}`
        : "test cases, then an evaluation",
    }));
}
