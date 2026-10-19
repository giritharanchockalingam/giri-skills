/* POST /api/agent-runs/{id}/step — execute the next step of a running agent (one step per request). */
import { apiContext, apiError, json } from "@/lib/factory/http";
import { advanceAgentRun, type AgentRunRow, type AgentVersionRow } from "@/lib/factory/agentRun";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  const { id } = await params;
  const { data: run, error } = await ctx.supabase.from("sf_agent_runs").select("*").eq("id", id).eq("workspace_id", ctx.workspace.id).maybeSingle();
  if (error) return apiError(500, "query_failed", error.message);
  if (!run) return apiError(404, "not_found", "Run not found.");
  const r = run as AgentRunRow;
  if (r.invoked_by !== ctx.user.id && !["reviewer", "admin"].includes(ctx.role)) return apiError(403, "forbidden", "Only the person who started the run (or a reviewer/admin) can advance it.");
  if (r.status !== "running") return json(summary(r));
  const { data: v, error: ve } = await ctx.supabase.from("sf_agent_versions").select("*").eq("id", r.agent_version_id).single();
  if (ve) return apiError(500, "query_failed", ve.message);
  try {
    const next = await advanceAgentRun(ctx, r, (v as AgentVersionRow).spec);
    if (next.status !== "running" && next.status !== "awaiting_approval") {
      await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "agent.run.finish", p_entity_type: "agent_run", p_entity_id: r.id, p_details: { status: next.status, steps: next.steps.length, cost_usd: next.cost_usd } });
    }
    return json(summary(next));
  } catch (e) {
    return apiError(500, "step_failed", (e as Error).message);
  }
}

const summary = (r: AgentRunRow) => ({ run_id: r.id, status: r.status, cursor: r.cursor, error: r.error, steps: r.steps.map((s) => ({ id: s.id, kind: s.kind, status: s.status, checks_passed: s.checks_passed, checks_total: s.checks_total, error: s.error ?? null })) });
