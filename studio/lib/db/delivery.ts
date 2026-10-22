/* Data access for delivery metrics: the latest snapshot per repository (RLS-scoped). */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Delivery } from "@/lib/insights/delivery";

export interface DeliveryRow { entity_id: string; key: string; computed_at: string; notes: string[]; d30: Delivery; d90: Delivery }

export async function loadDelivery(sb: SupabaseClient, ws: string, entityId?: string): Promise<DeliveryRow[]> {
  let q = sb.from("sf_delivery_latest").select("entity_id, computed_at, notes, metrics").eq("workspace_id", ws);
  if (entityId) q = q.eq("entity_id", entityId);
  const [{ data }, { data: ents }] = await Promise.all([q, sb.from("sf_catalog_entities").select("id, key, archived").eq("workspace_id", ws).eq("kind", "repository")]);
  const key = new Map(((ents ?? []) as { id: string; key: string; archived: boolean }[]).filter((e) => !e.archived).map((e) => [e.id, e.key]));
  return ((data ?? []) as { entity_id: string; computed_at: string; notes: string[]; metrics: { d30: Delivery; d90: Delivery } }[])
    .filter((r) => key.has(r.entity_id))
    .map((r) => ({ entity_id: r.entity_id, key: key.get(r.entity_id)!, computed_at: r.computed_at, notes: r.notes ?? [], d30: r.metrics.d30, d90: r.metrics.d90 }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

/* ───────────── delivery runs (0022): the control plane for docs/DELIVERY-PIPELINES.md ─────────────
 * Session paths run as the signed-in user (RLS); writes go through the SECURITY DEFINER RPCs that re-check the
 * caller (sf_delivery_run_start, sf_delivery_run_set_stage). API-key paths pass the key hash to the same RPCs. */
import type { DeliveryApproval, DeliveryRun, StagePost } from "@/lib/delivery/core";

export interface DeliveryRunStartPayload {
  workspace_id?: string; pipeline: string; pipeline_version: string; mode: string; repo: string; ref: string; request: string; executor: string; stages: unknown[];
}
export interface StagePatch { status?: string; stage?: string; stack_profile?: unknown; pr?: unknown; executor_ref?: string; error?: string | null }
type Rpc = { data: unknown; error: { message: string } | null };
const rpcRun = (r: Rpc, what: string): DeliveryRun => {
  if (r.error) throw new Error(`${what}: ${r.error.message}`);
  const d = r.data as Record<string, unknown> | null;
  if (!d) throw new Error(`${what}: not found`);
  if (typeof d.error === "string" && !("id" in d)) throw new Error(`${d.error}: ${typeof d.message === "string" ? d.message : "refused"}`);
  return d as unknown as DeliveryRun;
};

/** Starts a run (status queued) after the database's access rule; audited there. Throws `not_in_role: …` on refusal. */
export async function startDeliveryRun(sb: SupabaseClient, payload: DeliveryRunStartPayload, keyHash?: string): Promise<DeliveryRun> {
  return rpcRun(await sb.rpc("sf_delivery_run_start", { p_payload: payload, ...(keyHash ? { p_key_hash: keyHash } : {}) }), "start delivery run");
}

/** Merges one stage record into the run and applies the run-level patch the reducer computed. */
export async function setDeliveryStage(sb: SupabaseClient, runId: string, stage: StagePost, patch: StagePatch, keyHash?: string): Promise<DeliveryRun> {
  return rpcRun(await sb.rpc("sf_delivery_run_set_stage", { p_run: runId, p_stage: stage, p_patch: patch, ...(keyHash ? { p_key_hash: keyHash } : {}) }), "set delivery stage");
}

export async function getDeliveryRun(sb: SupabaseClient, ws: string, id: string): Promise<DeliveryRun | null> {
  const { data } = await sb.from("sf_delivery_runs").select("*").eq("workspace_id", ws).eq("id", id).maybeSingle();
  return (data ?? null) as DeliveryRun | null;
}

/** API-key read: the run with its approvals, or null when the key's workspace has no such run. */
export async function getDeliveryRunByKey(sb: SupabaseClient, keyHash: string, id: string): Promise<(DeliveryRun & { approvals: DeliveryApproval[] }) | null> {
  const { data, error } = await sb.rpc("sf_api_delivery_get", { p_key_hash: keyHash, p_run: id });
  if (error) throw new Error(`get delivery run: ${error.message}`);
  return (data ?? null) as (DeliveryRun & { approvals: DeliveryApproval[] }) | null;
}

export async function listDeliveryRuns(sb: SupabaseClient, ws: string, limit = 100): Promise<DeliveryRun[]> {
  const { data } = await sb.from("sf_delivery_runs").select("*").eq("workspace_id", ws).order("created_at", { ascending: false }).limit(limit);
  return (data ?? []) as DeliveryRun[];
}

export async function listDeliveryApprovals(sb: SupabaseClient, runId: string): Promise<DeliveryApproval[]> {
  const { data } = await sb.from("sf_delivery_approvals").select("*").eq("run_id", runId).order("created_at");
  return (data ?? []) as DeliveryApproval[];
}

export async function insertDeliveryApproval(sb: SupabaseClient, row: { run_id: string; stage_id: string; role: string; approved_by: string; note: string }): Promise<DeliveryApproval> {
  const { data, error } = await sb.from("sf_delivery_approvals").insert(row).select("*").single();
  if (error) throw new Error(`record approval: ${error.message}`);
  return data as DeliveryApproval;
}

/** Non-evidence columns an operator may still change (executor notice, error line). */
export async function noteDeliveryRun(sb: SupabaseClient, runId: string, patch: { executor_ref?: string; error?: string | null }, keyHash?: string): Promise<void> {
  const { error } = await sb.rpc("sf_delivery_run_set_stage", { p_run: runId, p_stage: null, p_patch: patch, ...(keyHash ? { p_key_hash: keyHash } : {}) });
  if (error) throw new Error(`note delivery run: ${error.message}`);
}

/** Role slugs sf_pipeline_access lists per pipeline (empty = open to every member). */
export async function listPipelineAccess(sb: SupabaseClient, ws: string): Promise<Map<string, string[]>> {
  const { data } = await sb.from("sf_pipeline_access").select("pipeline, role_slug").eq("workspace_id", ws);
  const out = new Map<string, string[]>();
  for (const r of (data ?? []) as { pipeline: string; role_slug: string }[]) out.set(r.pipeline, [...(out.get(r.pipeline) ?? []), r.role_slug]);
  return out;
}

/** Slugs of the job roles assigned to a member (sf_role_assignments → sf_talent). */
export async function listUserRoleSlugs(sb: SupabaseClient, ws: string, userId: string): Promise<string[]> {
  const { data } = await sb.from("sf_role_assignments").select("sf_talent!inner(slug, kind)").eq("workspace_id", ws).eq("user_id", userId);
  return ((data ?? []) as unknown as { sf_talent: { slug: string; kind: string } | { slug: string; kind: string }[] }[])
    .flatMap((r) => (Array.isArray(r.sf_talent) ? r.sf_talent : [r.sf_talent])).filter((t) => t?.kind === "role").map((t) => t.slug);
}

/** Display names for approvers (the workspace member directory; falls back to the id). */
export async function memberEmails(sb: SupabaseClient, ws: string): Promise<Map<string, string>> {
  const { data } = await sb.rpc("sf_member_directory", { p_workspace: ws });
  return new Map(((data ?? []) as { user_id: string; email: string | null }[]).map((m) => [m.user_id, m.email ?? m.user_id]));
}
