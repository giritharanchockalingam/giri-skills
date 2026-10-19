/* POST /api/agent-runs — start a run of an agent version with the given inputs (validated against the agent's
 * declared inputs). The client then calls /api/agent-runs/{id}/step until the run leaves "running". */
import { apiContext, apiError, json, readJson } from "@/lib/factory/http";
import { can } from "@/lib/factory/roles";
import type { AgentVersionRow } from "@/lib/factory/agentRun";
import type { StoredInput } from "@/lib/factory/agents";

export const dynamic = "force-dynamic";
const MAX_INPUT_BYTES = 2_000_000;

export async function POST(req: Request) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  const body = await readJson(req);
  if (!body) return apiError(400, "bad_request", "Body must be a JSON object.");
  const { data: v, error } = await ctx.supabase.from("sf_agent_versions")
    .select("*, sf_agents!inner(id, workspace_id, slug)").eq("id", String(body.version_id ?? "")).maybeSingle();
  if (error) return apiError(500, "query_failed", error.message);
  const version = v as (AgentVersionRow & { sf_agents: { id: string; workspace_id: string; slug: string } }) | null;
  if (!version || version.sf_agents.workspace_id !== ctx.workspace.id) return apiError(404, "not_found", "Agent version not found in this workspace.");
  if (!can(ctx.role, version.status === "published" ? "run.published" : "run.any_version")) return apiError(403, "forbidden", `Your role (${ctx.role}) can only run published agents.`);

  const raw = (body.inputs ?? {}) as Record<string, unknown>;
  const inputs: Record<string, StoredInput> = {};
  const problems: string[] = [];
  for (const decl of version.spec.inputs) {
    const val = raw[decl.name];
    if (val == null || (typeof val === "object" && !("kind" in (val as object)))) { if (decl.required) problems.push(`${decl.name}: required`); continue; }
    const vv = val as StoredInput;
    if (vv.kind === "text") {
      if (typeof vv.content !== "string" || !vv.content.trim()) { if (decl.required) problems.push(`${decl.name}: empty`); continue; }
      if (Buffer.byteLength(vv.content) > MAX_INPUT_BYTES) { problems.push(`${decl.name}: larger than 2 MB`); continue; }
      inputs[decl.name] = { kind: "text", content: vv.content, ext: String(vv.ext ?? decl.type).replace(/[^a-z0-9]/gi, "").slice(0, 8) || "txt" };
    } else if (vv.kind === "value") {
      const s = String(vv.value ?? "").slice(0, 2000);
      if (!s.trim()) { if (decl.required) problems.push(`${decl.name}: empty`); continue; }
      inputs[decl.name] = { kind: "value", value: s };
    } else problems.push(`${decl.name}: unsupported input kind`);
  }
  for (const k of Object.keys(raw)) if (!version.spec.inputs.some((d) => d.name === k)) problems.push(`${k}: not an input of this agent`);
  if (problems.length) return apiError(400, "invalid_inputs", "Some inputs are missing or invalid.", problems);

  const { data: run, error: ie } = await ctx.supabase.from("sf_agent_runs")
    .insert({ workspace_id: ctx.workspace.id, agent_version_id: version.id, invoked_by: ctx.user.id, inputs }).select("id").single();
  if (ie) return apiError(403, "rejected", ie.message);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "agent.run.start", p_entity_type: "agent_run", p_entity_id: run.id,
    p_details: { agent: version.sf_agents.slug, version: version.version, spec_hash: version.spec_hash } });
  return json({ run_id: run.id }, 201);
}
