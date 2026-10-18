/* POST /api/eval-runs {version_id} — starts an evaluation run: snapshots the case set (hash + ids) and returns the run id.
 * The client then calls POST /api/eval-runs/{id}/step once per case (each case runs within the function's deadline);
 * progress is durable in sf_eval_runs.results, so a closed tab can resume. */
import { apiContext, apiError, json, readJson } from "@/lib/factory/http";
import { can } from "@/lib/factory/roles";
import type { EvalCaseRow, VersionRow } from "@/lib/factory/db";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  if (!can(ctx.role, "eval.run")) return apiError(403, "forbidden", `Your role (${ctx.role}) cannot run evaluations.`);
  const body = await readJson(req);
  const versionId = String(body?.version_id ?? "");
  const { data: v } = await ctx.supabase.from("sf_skill_versions").select("id, status, manifest, sf_skills(workspace_id)").eq("id", versionId).maybeSingle();
  const version = v as (Pick<VersionRow, "id" | "status" | "manifest"> & { sf_skills: { workspace_id: string } }) | null;
  if (!version || version.sf_skills.workspace_id !== ctx.workspace.id) return apiError(404, "not_found", "Version not found.");
  if (version.status === "retired" || version.status === "superseded") return apiError(409, "not_runnable", `Version is ${version.status}.`);
  const { data: cases } = await ctx.supabase.from("sf_eval_cases").select("id, name").eq("version_id", versionId).order("created_at");
  if (!cases?.length) return apiError(409, "no_cases", "This version has no evaluation cases. Add at least one first.");
  const { data: hash, error: he } = await ctx.supabase.rpc("sf_eval_set_hash", { p_version: versionId });
  if (he) return apiError(500, "hash_failed", he.message);
  const results = (cases as Pick<EvalCaseRow, "id" | "name">[]).map((c) => ({ case_id: c.id, name: c.name, run_id: null, status: "pending", passed: 0, total: 0, checks: [], error: null, duration_ms: 0 }));
  const { data: run, error } = await ctx.supabase.from("sf_eval_runs").insert({
    version_id: versionId, eval_set_hash: String(hash), status: "running", results, created_by: ctx.user.id,
    provider: version.manifest.model_config.provider, model: version.manifest.model_config.provider === "none" ? null : version.manifest.model_config.model,
  }).select("id").single();
  if (error) return apiError(500, "insert_failed", error.message);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "eval.start", p_entity_type: "eval_run", p_entity_id: run.id, p_details: { version_id: versionId, cases: cases.length, eval_set_hash: hash } });
  return json({ eval_run_id: run.id, cases: cases.length, eval_set_hash: hash }, 201);
}
