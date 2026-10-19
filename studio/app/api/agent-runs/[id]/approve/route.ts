/* POST /api/agent-runs/{id}/approve — a reviewer or admin approves the approval step the run is waiting on. */
import { apiContext, apiError, json, readJson } from "@/lib/factory/http";
import { approveAgentRun, type AgentRunRow } from "@/lib/factory/agentRun";

export const dynamic = "force-dynamic";

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  if (!["reviewer", "admin"].includes(ctx.role)) return apiError(403, "forbidden", "Reviewers or admins approve agent steps.");
  const { id } = await params;
  const body = (await readJson(req)) ?? {};
  const { data: run } = await ctx.supabase.from("sf_agent_runs").select("*").eq("id", id).eq("workspace_id", ctx.workspace.id).maybeSingle();
  if (!run) return apiError(404, "not_found", "Run not found.");
  try {
    const next = await approveAgentRun(ctx.supabase, run as AgentRunRow, { id: ctx.user.id, email: ctx.user.email }, String(body.note ?? ""));
    const step = next.steps.find((s) => s.kind === "approval" && s.approver_id === ctx.user.id && s.at);
    await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "agent.run.approve", p_entity_type: "agent_run", p_entity_id: id, p_details: { step: step?.id, role: step?.role, note: step?.approval_note } });
    return json({ run_id: id, status: next.status });
  } catch (e) {
    return apiError(409, "conflict", (e as Error).message);
  }
}
