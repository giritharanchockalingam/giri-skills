/* Delivery runs — the server-side flows shared by the REST routes, the Deliver page's actions and the MCP tools.
 * Pure decisions live in ./core; database access in lib/db/delivery.ts; executor hand-off in ./dispatch. */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { WsCtx } from "@/lib/factory/db";
import type { DeliveryStartInput, DeliveryStageInput } from "@/lib/validation";
import { applyStage, approvalPost, awaitingStage, canApproveStage, canStartPipeline, deliverCommand, seedStages, type DeliveryRun, type StagePost } from "./core";
import { dispatch } from "./dispatch";
import { pipelineByName } from "./pipelines";
import { getDeliveryRun, insertDeliveryApproval, listPipelineAccess, listUserRoleSlugs, noteDeliveryRun, setDeliveryStage, startDeliveryRun } from "@/lib/db/delivery";

export class DeliveryError extends Error { constructor(public status: number, public code: string, message: string) { super(message); } }

export interface StartResult { run: DeliveryRun; command: string; notice: string | null }
export const callbackUrl = (portalUrl: string, runId: string) => `${portalUrl.replace(/\/+$/, "")}/api/delivery-runs/${runId}/stage`;

/** Starts a run for a session caller (the database re-checks sf_pipeline_access and audits delivery.start), then
 *  hands it to the executor. A missing executor is a recorded notice, never a pretended dispatch. */
export async function startForSession(ctx: WsCtx, input: DeliveryStartInput, portalUrl: string): Promise<StartResult> {
  const p = pipelineByName(input.pipeline);
  if (!p) throw new DeliveryError(404, "unknown_pipeline", `No pipeline template named “${input.pipeline}”.`);
  const [access, job] = await Promise.all([listPipelineAccess(ctx.supabase, ctx.workspace.id), listUserRoleSlugs(ctx.supabase, ctx.workspace.id, ctx.user.id)]);
  if (!canStartPipeline({ member: ctx.role, job }, access.get(p.name) ?? [])) throw new DeliveryError(403, "not_in_role", "This pipeline is not open to any role assigned to you. Ask an administrator for access.");
  let run: DeliveryRun;
  try {
    run = await startDeliveryRun(ctx.supabase, { workspace_id: ctx.workspace.id, pipeline: p.name, pipeline_version: p.version, mode: p.mode, repo: input.repo, ref: input.ref, request: input.request, executor: input.executor, stages: seedStages(p) });
  } catch (e) { throw asDeliveryError(e); }
  return afterStart(ctx.supabase, run, portalUrl);
}

/** The same for an API-key caller (MCP `deliver`): the key's workspace, the key's job roles, audited as the key. */
export async function startForKey(sb: SupabaseClient, keyHash: string, input: DeliveryStartInput, portalUrl: string): Promise<StartResult> {
  const p = pipelineByName(input.pipeline);
  if (!p) throw new DeliveryError(404, "unknown_pipeline", `No pipeline template named “${input.pipeline}”.`);
  let run: DeliveryRun;
  try {
    run = await startDeliveryRun(sb, { pipeline: p.name, pipeline_version: p.version, mode: p.mode, repo: input.repo, ref: input.ref, request: input.request, executor: input.executor, stages: seedStages(p) }, keyHash);
  } catch (e) { throw asDeliveryError(e); }
  return afterStart(sb, run, portalUrl, keyHash);
}

async function afterStart(sb: SupabaseClient, run: DeliveryRun, portalUrl: string, keyHash?: string): Promise<StartResult> {
  const command = deliverCommand(run, portalUrl);
  const d = await dispatch(run, { callbackUrl: callbackUrl(portalUrl, run.id), portalUrl });
  const executor_ref = d.ok ? d.executor_ref : d.notice ?? "";
  const notice = d.ok ? null : d.notice ?? null;
  if (executor_ref) {
    try { await noteDeliveryRun(sb, run.id, { executor_ref }, keyHash); } catch { /* the run exists; the notice is also returned to the caller */ }
    run = { ...run, executor_ref };
  }
  return { run, command, notice };
}

/** One stage record from the executor: reducer → status, persisted through the RPC (session member or API key). */
export async function recordStage(sb: SupabaseClient, run: DeliveryRun, input: DeliveryStageInput, keyHash?: string): Promise<DeliveryRun> {
  if (run.status === "succeeded") throw new DeliveryError(409, "immutable", "This run succeeded; its evidence is immutable.");
  const { stack_profile, pr, executor_ref, ...stage } = input;
  const next = applyStage(run, stage as StagePost);
  const patch = { status: next.status, stage: next.stage ?? undefined, error: next.error, ...(stack_profile ? { stack_profile } : {}), ...(pr ? { pr } : {}), ...(executor_ref ? { executor_ref } : {}) };
  try { return await setDeliveryStage(sb, run.id, stage as StagePost, patch, keyHash); } catch (e) { throw asDeliveryError(e); }
}

/** A person approves the stage the run waits on: authority = admin or a holder of the stage's role; recorded, then applied. */
export async function approveStage(ctx: WsCtx, runId: string, stageId: string, note: string): Promise<DeliveryRun> {
  const run = await getDeliveryRun(ctx.supabase, ctx.workspace.id, runId);
  if (!run) throw new DeliveryError(404, "not_found", "Run not found.");
  const waiting = awaitingStage(run);
  if (!waiting || waiting.id !== stageId) throw new DeliveryError(409, "not_waiting", waiting ? `The run is waiting on “${waiting.id}”, not “${stageId}”.` : "This run is not waiting for an approval.");
  const job = await listUserRoleSlugs(ctx.supabase, ctx.workspace.id, ctx.user.id);
  if (!canApproveStage({ member: ctx.role, job }, waiting)) throw new DeliveryError(403, "forbidden", `Only a member assigned to the ${waiting.role || "owning"} role (or an admin) approves this stage.`);
  await insertDeliveryApproval(ctx.supabase, { run_id: run.id, stage_id: waiting.id, role: waiting.role, approved_by: ctx.user.id, note });
  const post = approvalPost(waiting, ctx.user.email ?? ctx.user.id, note, new Date().toISOString());
  const next = applyStage(run, post);
  try { return await setDeliveryStage(ctx.supabase, run.id, post, { status: next.status, stage: next.stage ?? undefined, error: next.error }); } catch (e) { throw asDeliveryError(e); }
}

function asDeliveryError(e: unknown): DeliveryError {
  if (e instanceof DeliveryError) return e;
  const msg = e instanceof Error ? e.message : String(e);
  if (/^not_in_role|^not_member/.test(msg)) return new DeliveryError(403, "not_in_role", msg.replace(/^[a-z_]+: /, ""));
  if (/immutable/.test(msg)) return new DeliveryError(409, "immutable", msg.replace(/^[a-z ]+: /, ""));
  if (/not found/.test(msg)) return new DeliveryError(404, "not_found", msg);
  return new DeliveryError(500, "delivery_failed", msg);
}
