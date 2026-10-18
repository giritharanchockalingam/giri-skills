/* Interpretation of a sf_version_release_state row: the gates, in plain language, and the single next action.
 * The database decides (sf_publish_version re-checks everything); this only explains. Pure module. */
export type VersionStatus = "draft" | "in_review" | "approved" | "published" | "superseded" | "retired";

export interface ReleaseStateRow {
  version_id: string; status: VersionStatus; manifest_hash: string;
  min_eval_pass_rate: number | string | null; require_approval: boolean; eval_case_count: number;
  current_eval_set_hash: string | null;
  latest_eval_run_id: string | null; latest_eval_pass_rate: number | string | null; latest_eval_set_hash: string | null; latest_eval_at: string | null;
  eval_current: boolean | null; eval_gate_met: boolean | null;
  latest_approval_id: string | null; latest_approval_decision: "approve" | "reject" | null; latest_approval_hash: string | null;
  latest_approval_at: string | null; latest_approval_reviewer: string | null; latest_approval_note: string | null;
  approval_valid: boolean | null; approval_stale: boolean | null; publishable: boolean | null;
}

export type Tone = "sage" | "hold" | "rust" | "none";
export interface Gate { key: "eval" | "approval"; label: string; tone: Tone; met: boolean; detail: string; /** ≤ 6 words for compact views */ short: string }

const num = (v: number | string | null | undefined) => (v == null ? null : typeof v === "number" ? v : Number(v));
export const pct = (v: number | string | null | undefined) => { const n = num(v); return n == null ? "—" : `${Math.round(n * 100)}%`; };

export function evalGate(r: ReleaseStateRow): Gate {
  const min = num(r.min_eval_pass_rate) ?? 0;
  if (min <= 0) return { key: "eval", label: "Evaluation gate", tone: "none", met: true, detail: "No minimum pass rate is set for this version (release_criteria.min_eval_pass_rate = 0).", short: "no minimum set" };
  if (r.eval_case_count === 0) return { key: "eval", label: "Evaluation gate", tone: "rust", met: false, detail: `Requires ≥ ${pct(min)} pass rate, but this version has no evaluation cases yet.`, short: `no cases · needs ≥ ${pct(min)}` };
  if (!r.latest_eval_run_id) return { key: "eval", label: "Evaluation gate", tone: "rust", met: false, detail: `Requires ≥ ${pct(min)} pass rate; no evaluation has been run on this version.`, short: `${r.eval_case_count} cases not run · needs ≥ ${pct(min)}` };
  if (!r.eval_current) return { key: "eval", label: "Evaluation gate", tone: "hold", met: false, detail: `The latest evaluation (${pct(r.latest_eval_pass_rate)}) ran on an older case set — the cases changed since. Run the evaluation again.`, short: "cases changed · re-run" };
  const rate = num(r.latest_eval_pass_rate) ?? 0;
  if (rate < min) return { key: "eval", label: "Evaluation gate", tone: "rust", met: false, detail: `Latest pass rate ${pct(rate)} is below the required ${pct(min)}.`, short: `${pct(rate)} < ${pct(min)} required` };
  return { key: "eval", label: "Evaluation gate", tone: "sage", met: true, detail: `Latest pass rate ${pct(rate)} meets the required ${pct(min)} on the current case set.`, short: `${pct(rate)} ≥ ${pct(min)}` };
}

export function approvalGate(r: ReleaseStateRow): Gate {
  if (!r.require_approval) return { key: "approval", label: "Approval", tone: "none", met: true, detail: "This version does not require a reviewer's approval (release_criteria.require_approval = false).", short: "not required" };
  if (r.approval_valid) return { key: "approval", label: "Approval", tone: "sage", met: true, detail: `Approved on the current manifest (hash ${r.manifest_hash.slice(0, 12)}…).`, short: "approved · current manifest" };
  if (r.approval_stale) return { key: "approval", label: "Approval", tone: "hold", met: false, detail: `Stale: the manifest changed after approval (approved ${r.latest_approval_hash?.slice(0, 12)}…, now ${r.manifest_hash.slice(0, 12)}…). Request review again.`, short: "stale · manifest changed" };
  if (r.latest_approval_decision === "reject") return { key: "approval", label: "Approval", tone: "rust", met: false, detail: `Rejected by a reviewer${r.latest_approval_note ? `: “${r.latest_approval_note}”` : ""}. Fix the draft and request review again.`, short: "rejected" };
  if (r.status === "in_review") return { key: "approval", label: "Approval", tone: "hold", met: false, detail: "Waiting for a reviewer's decision.", short: "waiting for reviewer" };
  return { key: "approval", label: "Approval", tone: "rust", met: false, detail: "No approval yet. Request review when the evaluation evidence is ready.", short: "none yet" };
}

export interface NextAction { label: string; action: "edit" | "test" | "add_cases" | "run_eval" | "request_review" | "review" | "publish" | "new_draft" | "none"; who: "author" | "reviewer" | "anyone" }

/** The one primary action for the version's current state. */
export function nextAction(r: ReleaseStateRow, hasRuns: boolean): NextAction {
  if (r.status === "published") return { label: "Create improved draft", action: "new_draft", who: "author" };
  if (r.status === "superseded" || r.status === "retired") return { label: "Create improved draft", action: "new_draft", who: "author" };
  if (r.status === "in_review") return { label: "Review results", action: "review", who: "reviewer" };
  const eg = evalGate(r), ag = approvalGate(r);
  if (r.status === "approved" && eg.met && ag.met) return { label: "Publish version", action: "publish", who: "author" };
  if (!hasRuns) return { label: "Test skill", action: "test", who: "author" };
  if (!eg.met) {
    if (r.eval_case_count === 0) return { label: "Add evaluation cases", action: "add_cases", who: "author" };
    return { label: "Run evaluation", action: "run_eval", who: "author" };
  }
  if (!ag.met) return { label: "Request review", action: "request_review", who: "author" };
  return { label: "Publish version", action: "publish", who: "author" };
}

export const STATUS_LABEL: Record<VersionStatus, string> = {
  draft: "Draft", in_review: "In review", approved: "Approved", published: "Published", superseded: "Superseded", retired: "Retired",
};
export const STATUS_TONE: Record<VersionStatus, Tone> = {
  draft: "none", in_review: "hold", approved: "sage", published: "sage", superseded: "none", retired: "rust",
};
