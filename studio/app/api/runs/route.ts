/* POST /api/runs — "Test skill" from the UI: validate inputs, create the run row (policy checks in sf_run_insert),
 * execute through the Python runtime, persist the outcome. Synchronous within the manifest's deadline. */
import { apiContext, apiError, json, readJson } from "@/lib/factory/http";
import { validateInputs, describeInputs } from "@/lib/factory/schema";
import { sha256 } from "@/lib/factory/hash";
import { executeRun } from "@/lib/factory/runtime";
import { getPolicy, must, type VersionRow } from "@/lib/factory/db";
import { can } from "@/lib/factory/roles";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  const body = await readJson(req);
  if (!body) return apiError(400, "bad_request", "Body must be a JSON object.");
  const versionId = String(body.version_id ?? "");
  const { data: v } = await ctx.supabase.from("sf_skill_versions").select("*, sf_skills(id, slug, workspace_id)").eq("id", versionId).maybeSingle();
  const version = v as (VersionRow & { sf_skills: { id: string; slug: string; workspace_id: string } }) | null;
  if (!version || version.sf_skills.workspace_id !== ctx.workspace.id) return apiError(404, "not_found", "Version not found in this workspace.");
  if (!can(ctx.role, version.status === "published" ? "run.published" : "run.any_version")) return apiError(403, "forbidden", `Your role (${ctx.role}) can only run published versions.`);
  if (version.status === "retired" || version.status === "superseded") return apiError(409, "not_runnable", `Version is ${version.status}.`);

  const validated = validateInputs(version.manifest, body.inputs ?? {});
  const assumptions: Record<string, string> = {};
  const rawAssume = (body.assumptions ?? {}) as Record<string, unknown>;
  for (const [k, val] of Object.entries(rawAssume)) if (typeof val === "string" && val.trim() && version.manifest.inputs.some((i) => i.name === k)) assumptions[k] = val.slice(0, 2000);
  const missing = validated.missing.filter((m) => !(m in assumptions));
  if (validated.problems.length) return apiError(400, "invalid_inputs", "Some inputs are invalid.", validated.problems);
  if (missing.length) return apiError(400, "missing_inputs", `Required input(s) missing: ${missing.join(", ")}. Provide them or an assumption.`, { missing });

  const idem = req.headers.get("idempotency-key")?.slice(0, 120) || null;
  const { data: created, error } = await ctx.supabase.rpc("sf_run_insert", { p_version: versionId, p_source: "ui", p_inputs_ref: describeInputs(validated.inputs, sha256), p_idempotency_key: idem });
  if (error) return apiError(error.message.includes("limit") || error.message.includes("budget") ? 429 : 403, "rejected", error.message);
  const runId = String(created.run_id);
  if (created.existing) {
    const { data: ex } = await ctx.supabase.from("sf_runs").select("id, status, error").eq("id", runId).single();
    return json({ run_id: runId, status: ex?.status, error: ex?.error, deduplicated: true }, 200);
  }
  await ctx.supabase.from("sf_runs").update({ status: "running", started_at: new Date().toISOString() }).eq("id", runId);
  const files = version.source.kind === "authored" ? (must(await ctx.supabase.from("sf_files").select("path, content").eq("version_id", versionId), "files") as { path: string; content: string }[]) : [];
  const patch = await executeRun({
    runId, manifest: version.manifest, source: version.source, slug: version.sf_skills.slug, files, inputs: validated.inputs, assumptions, policy: await getPolicy(ctx),
    isCancelled: async () => (await ctx.supabase.from("sf_runs").select("status").eq("id", runId).single()).data?.status === "cancelled",
  });
  const { response, ...row } = patch;
  const { error: ue } = await ctx.supabase.from("sf_runs").update(row).eq("id", runId);
  if (ue) return apiError(500, "persist_failed", `Run executed (${row.status}) but could not be saved: ${ue.message}`);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "run.finish", p_entity_type: "run", p_entity_id: runId, p_details: { status: row.status, provider: row.provider, model: row.model, duration_ms: row.duration_ms, cost_usd: row.cost_usd } });
  return json({ run_id: runId, status: row.status, error: row.error, provider: response?.provider ?? null, model: row.model, usage: row.usage, cost_usd: row.cost_usd, cost_is_estimate: row.cost_is_estimate, duration_ms: row.duration_ms, deduplicated: false });
}
