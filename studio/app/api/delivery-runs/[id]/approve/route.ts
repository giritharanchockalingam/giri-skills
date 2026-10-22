/* POST /api/delivery-runs/{id}/approve {stage_id, note} — a member assigned to the stage's role (or an admin) approves
 * the stage the run is waiting on. Recorded in sf_delivery_approvals, applied to the stage, audited (delivery.approve). */
import { apiContext, apiError, json, readJson } from "@/lib/factory/http";
import { DeliveryApproveInput, UUID } from "@/lib/validation";
import { DeliveryError, approveStage } from "@/lib/delivery/server";

export const dynamic = "force-dynamic";

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  const { id } = await params;
  if (!UUID.test(id)) return apiError(400, "bad_request", "run id must be a UUID");
  const body = await readJson(req);
  if (!body) return apiError(400, "bad_request", "Body must be a JSON object.");
  const parsed = DeliveryApproveInput.safeParse(body);
  if (!parsed.success) return apiError(400, "invalid_inputs", "stage_id is required.", parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`));
  try {
    const next = await approveStage(ctx, id, parsed.data.stage_id, parsed.data.note);
    await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "delivery.approve", p_entity_type: "delivery_run", p_entity_id: id, p_details: { stage: parsed.data.stage_id, note: parsed.data.note, status: next.status } });
    return json({ run_id: id, status: next.status, stage: next.stage });
  } catch (e) {
    if (e instanceof DeliveryError) return apiError(e.status, e.code, e.message);
    return apiError(500, "approve_failed", (e as Error).message);
  }
}
