/* Run the PUBLISHED version of a workspace skill for an API-key caller — shared by the REST API (/api/v1/skills/{slug}/run)
 * and the MCP server (/api/mcp). Contract first (inputs validated before anything is created), the same
 * concurrency / budget / idempotency rules as the UI (sf_record_run), output contract checked after. */
import type { ApiCaller } from "@/lib/factory/apikey";
import { stripRuntimePaths } from "@/lib/factory/publicShape";
import { validateInputs, describeInputs } from "@/lib/factory/schema";
import { sha256 } from "@/lib/factory/hash";
import { executeRun } from "@/lib/factory/runtime";
import { validateManifest } from "@/lib/factory/manifest";
import type { PolicyRow } from "@/lib/factory/db";

export interface ApiRunOutcome { http: number; body: Record<string, unknown> }
const err = (http: number, code: string, message: string, details?: unknown): ApiRunOutcome => ({ http, body: { error: { code, message, ...(details !== undefined ? { details } : {}) } } });

export async function runPublishedSkill(caller: ApiCaller, slug: string, body: Record<string, unknown> | null, idem: string | null, statusBase: string): Promise<ApiRunOutcome> {
  if (!body) return err(400, "bad_request", "Body must be a JSON object: {\"inputs\": {...}, \"assumptions\": {...}}.");

  // contract first: validate before creating anything
  const { data: pub, error: pe } = await caller.supabase.rpc("sf_api_skill", { p_key_hash: caller.keyHash, p_slug: slug });
  if (pe) return err(500, "query_failed", pe.message);
  if (!pub) return err(409, "not_published", `“${slug}” has no published version. Only published versions can be invoked.`);
  const mv = validateManifest(pub.manifest);
  if (!mv.ok) return err(500, "bad_manifest", "The published manifest failed validation on the server.", mv.problems);
  const manifest = mv.manifest;
  const validated = validateInputs(manifest, body.inputs ?? {});
  const assumptions: Record<string, string> = {};
  for (const [k, val] of Object.entries((body.assumptions ?? {}) as Record<string, unknown>)) if (typeof val === "string" && val.trim() && manifest.inputs.some((i) => i.name === k)) assumptions[k] = val.slice(0, 2000);
  const missing = validated.missing.filter((m) => !(m in assumptions));
  if (validated.problems.length) return err(400, "invalid_inputs", "Some inputs are invalid.", validated.problems);
  if (missing.length) return err(400, "missing_inputs", `Required input(s) missing: ${missing.join(", ")}.`, { missing });

  const { data: created, error } = await caller.supabase.rpc("sf_record_run", { p_key_hash: caller.keyHash, p_slug: slug, p_inputs_ref: describeInputs(validated.inputs, sha256), p_idempotency_key: idem });
  if (error) return err(error.message.includes("limit") || error.message.includes("budget") ? 429 : 409, "rejected", error.message);
  const runId = String(created.run_id);
  const statusUrl = new URL(`/api/v1/runs/${runId}`, statusBase).toString();
  if (created.existing) {
    const { data: ex } = await caller.supabase.rpc("sf_api_run_get", { p_key_hash: caller.keyHash, p_run: runId });
    return { http: 200, body: { run_id: runId, deduplicated: true, status: ex?.status ?? "unknown", status_url: statusUrl } };
  }
  const patchRun = (patch: Record<string, unknown>) => caller.supabase.rpc("sf_api_run_update", { p_key_hash: caller.keyHash, p_run: runId, p_patch: patch });
  await patchRun({ status: "running", started_at: new Date().toISOString() });
  // files for authored skills are not exposed through the API RPC; fetch via the same definer path
  const files: { path: string; content: string }[] = Array.isArray(pub.files) ? pub.files : [];
  const policy = (pub.policy ?? null) as PolicyRow | null;
  const patch = await executeRun({ runId, manifest, source: pub.source, slug, files, inputs: validated.inputs, assumptions, policy, status: "published" });
  const { response, ...row } = patch;
  const { error: ue } = await patchRun(row as unknown as Record<string, unknown>);
  if (ue) return err(500, "persist_failed", `Run executed (${row.status}) but could not be saved: ${ue.message}`);
  const result = {
    run_id: runId, status: row.status, skill: slug, version: pub.version, version_id: pub.version_id, manifest_hash: pub.manifest_hash,
    error: row.error, provider: response?.provider ?? null, model: row.model, usage: row.usage,
    cost: { usd: row.cost_usd, is_estimate: row.cost_is_estimate, basis: response?.cost.basis ?? null }, duration_ms: row.duration_ms,
    outputs: row.outputs, checks: (row.run_json?.checks as unknown[]) ?? [], steps: (row.run_json?.steps as unknown[]) ?? [], needs_input: response?.needs_input ?? null,
    contract: (row.run_json as { factory?: { contract?: unknown } } | null)?.factory?.contract ?? null, status_url: statusUrl,
  };
  return { http: row.status === "timeout" ? 202 : 200, body: stripRuntimePaths(result) as Record<string, unknown> };
}
