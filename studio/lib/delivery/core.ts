/* Delivery runs — pure core (no I/O), shared by the API routes, the pages, the MCP tools and the tests.
 * Contract: docs/DELIVERY-PIPELINES.md. A run is one request through one pipeline template on one repository; the
 * executor posts one stage record at a time and this module decides what the run's status becomes. */

export type DeliveryStatus = "queued" | "running" | "awaiting_approval" | "blocked" | "failed" | "succeeded";
export type StageStatus = "queued" | "running" | "awaiting_approval" | "blocked" | "failed" | "succeeded" | "skipped";
export type Executor = "github-actions" | "ide" | "local";
export type PipelineMode = "brownfield" | "greenfield";
export const DELIVERY_STATUSES: readonly DeliveryStatus[] = ["queued", "running", "awaiting_approval", "blocked", "failed", "succeeded"];
export const STAGE_STATUSES: readonly StageStatus[] = ["queued", "running", "awaiting_approval", "blocked", "failed", "succeeded", "skipped"];
export const EXECUTORS: readonly Executor[] = ["github-actions", "ide", "local"];

export interface Gate { kind: string; verdict: "pass" | "fail" | "pending" | string; detail?: string }
export interface Evidence { path: string; sha256: string; bytes: number }
export interface StageRecord {
  id: string; adlc_stage: string; role: string; status: StageStatus;
  gate?: Gate | null; evidence?: Evidence[]; started_at?: string | null; finished_at?: string | null; error?: string | null;
}
/** What the executor posts: a partial stage record, merged by id into the run (DELIVERY-PIPELINES.md → Evidence). */
export type StagePost = Partial<StageRecord> & { id: string };

export interface PipelineStep { id: string; kind: string; skill?: string }
export interface PipelineStage { id: string; adlc_stage: string; role: string; steps: PipelineStep[]; gate: Record<string, unknown> }
export interface Pipeline {
  name: string; version: string; title: string; description: string; mode: PipelineMode;
  fits: { stacks: string[]; request_kinds: string[] };
  inputs: { name: string; type: string; required: boolean; from: string }[];
  stages: PipelineStage[];
}

export interface DeliveryRun {
  id: string; workspace_id: string; pipeline: string; pipeline_version: string; mode: PipelineMode; repo: string; ref: string; request: string;
  status: DeliveryStatus; stage: string | null; stages: StageRecord[]; stack_profile: Record<string, unknown> | null;
  pr: { number?: number; url?: string; head_sha?: string } | null; executor: Executor; executor_ref: string | null;
  /** The composed pipeline's JSON when the run was started from one (DELIVERY-PIPELINES.md → When no template fits); null for a template. */
  pipeline_spec?: Record<string, unknown> | null;
  created_by: string | null; api_key_id: string | null; created_at: string; updated_at: string; error: string | null;
}
export interface DeliveryApproval { id: string; run_id: string; stage_id: string; role: string; approved_by: string; note: string; created_at: string }

/** The stage records a new run starts with: every template stage, queued, owned by its role. */
export function seedStages(p: Pipeline): StageRecord[] {
  return p.stages.map((s) => ({ id: s.id, adlc_stage: s.adlc_stage, role: s.role, status: "queued", gate: null, evidence: [], started_at: null, finished_at: null }));
}

const TERMINAL: readonly DeliveryStatus[] = ["succeeded"];

/** The run after one stage record is merged in (by id; order kept; unknown ids appended).
 *  Status: a running stage → running; an approval wait → awaiting_approval; a failed gate → blocked; a stage error →
 *  failed; the last stage succeeded (and no other stage still pending) → succeeded; otherwise running. A succeeded run
 *  is immutable: the same run comes back unchanged (the database refuses the write too). */
export function applyStage(run: DeliveryRun, post: StagePost): DeliveryRun {
  if (TERMINAL.includes(run.status)) return run;
  const idx = run.stages.findIndex((s) => s.id === post.id);
  const prev = idx >= 0 ? run.stages[idx] : { id: post.id, adlc_stage: post.adlc_stage ?? post.id, role: post.role ?? "", status: "queued" as StageStatus };
  const merged: StageRecord = { ...prev, ...post, evidence: post.evidence ?? prev.evidence ?? [] };
  const stages = idx >= 0 ? run.stages.map((s, i) => (i === idx ? merged : s)) : [...run.stages, merged];
  const gateFailed = merged.gate?.verdict === "fail";
  let status: DeliveryStatus;
  if (merged.status === "failed" || merged.error) status = "failed";
  else if (gateFailed || merged.status === "blocked") status = "blocked";
  else if (merged.status === "awaiting_approval") status = "awaiting_approval";
  else if (merged.status === "running" || merged.status === "queued") status = "running";
  else {
    const last = stages[stages.length - 1];
    const allDone = stages.every((s) => s.status === "succeeded" || s.status === "skipped");
    status = last.id === merged.id && allDone ? "succeeded" : "running";
  }
  const error = status === "failed" ? merged.error ?? `stage ${merged.id} failed` : status === "blocked" ? merged.gate?.detail ?? `gate failed at ${merged.id}` : null;
  return { ...run, stages, stage: merged.id, status, error };
}

/** The approval record applied to the stage it was waiting on: the gate passes, the stage succeeds, the run moves on. */
export function approvalPost(stage: StageRecord, approver: string, note: string, at: string): StagePost {
  const detail = `approved by ${approver}${note ? ` — ${note}` : ""}`;
  return { id: stage.id, status: "succeeded", gate: { kind: "approval", verdict: "pass", detail }, finished_at: at };
}

/** Who may start a pipeline. `roles.member` is the workspace role, `roles.job` the slugs of job roles assigned to the
 *  caller; `access` is the role slugs sf_pipeline_access lists for that pipeline. Admins always; no rows = open. */
export function canStartPipeline(roles: { member: string | null; job: readonly string[] }, access: readonly string[]): boolean {
  if (!roles.member) return false;
  if (roles.member === "admin") return true;
  if (access.length === 0) return true;
  return roles.job.some((r) => access.includes(r));
}

/** Who may approve a stage: an admin, or a member assigned to the stage's owning role. */
export function canApproveStage(roles: { member: string | null; job: readonly string[] }, stage: Pick<StageRecord, "role">): boolean {
  if (!roles.member) return false;
  if (roles.member === "admin") return true;
  return !!stage.role && roles.job.includes(stage.role);
}

/** The stage a run is waiting on, if any. */
export const awaitingStage = (run: DeliveryRun): StageRecord | null =>
  run.status === "awaiting_approval" ? run.stages.find((s) => s.id === run.stage && s.status === "awaiting_approval") ?? run.stages.find((s) => s.status === "awaiting_approval") ?? null : null;

const sh = (s: string) => `'${s.replace(/'/g, `'\\''`)}'`;
/** The exact command to run the executor from an IDE for this run (evidence is posted back with the API key in SF_API_KEY). */
export function deliverCommand(run: Pick<DeliveryRun, "id" | "pipeline" | "repo" | "ref" | "request">, portalUrl: string): string {
  const parts = ["python3", "scripts/deliver.py", "--pipeline", run.pipeline, "--repo", sh(run.repo)];
  if (run.ref) parts.push("--ref", sh(run.ref));
  parts.push("--request", sh(run.request), "--run", run.id, "--portal", sh(portalUrl.replace(/\/+$/, "")));
  return parts.join(" ");
}

export const NO_EXECUTOR_NOTICE = "no executor configured — run `scripts/deliver.py` from an IDE and post evidence";

export const DELIVERY_LABEL: Record<DeliveryStatus, string> = { queued: "Queued", running: "Running", awaiting_approval: "Awaiting approval", blocked: "Blocked", failed: "Failed", succeeded: "Succeeded" };
export const DELIVERY_TONE: Record<DeliveryStatus, string> = { queued: "none", running: "deep", awaiting_approval: "hold", blocked: "hold", failed: "rust", succeeded: "sage" };
export const STAGE_LABEL: Record<StageStatus, string> = { queued: "queued", running: "running", awaiting_approval: "awaiting approval", blocked: "blocked", failed: "failed", succeeded: "done", skipped: "skipped" };
export const STAGE_TONE: Record<StageStatus, string> = { queued: "none", running: "deep", awaiting_approval: "hold", blocked: "hold", failed: "rust", succeeded: "sage", skipped: "none" };
