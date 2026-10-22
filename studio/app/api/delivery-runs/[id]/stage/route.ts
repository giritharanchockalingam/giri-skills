/* POST /api/delivery-runs/{id}/stage — the executor's callback: one stage record (status, gate verdict, evidence
 * hashes, optional stack_profile / pr). Auth: an API key of the workspace (GitHub Actions, scripts/deliver.py) or a
 * signed-in member. The reducer (lib/delivery/core applyStage) decides the run's status; the RPC persists and audits. */
import { apiContext, apiError, json, readJson } from "@/lib/factory/http";
import { authenticateApiKey } from "@/lib/factory/apikey";
import { DeliveryStageInput, UUID } from "@/lib/validation";
import { DeliveryError, recordStage } from "@/lib/delivery/server";
import { getDeliveryRun, getDeliveryRunByKey } from "@/lib/db/delivery";
import type { DeliveryRun } from "@/lib/delivery/core";

export const dynamic = "force-dynamic";

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!UUID.test(id)) return apiError(400, "bad_request", "run id must be a UUID");
  const body = await readJson(req);
  if (!body) return apiError(400, "bad_request", "Body must be a JSON object.");
  const parsed = DeliveryStageInput.safeParse(body);
  if (!parsed.success) return apiError(400, "invalid_stage", "The stage record is invalid.", parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`));
  let sb, run: DeliveryRun | null, keyHash: string | undefined;
  if (req.headers.get("authorization")) {
    const caller = await authenticateApiKey(req);
    if (caller instanceof Response) return caller;
    sb = caller.supabase; keyHash = caller.keyHash;
    run = await getDeliveryRunByKey(sb, keyHash, id);
  } else {
    const ctx = await apiContext();
    if (!ctx) return apiError(401, "unauthenticated", "Sign in, or send `Authorization: Bearer <api key>`.");
    sb = ctx.supabase;
    run = await getDeliveryRun(sb, ctx.workspace.id, id);
  }
  if (!run) return apiError(404, "not_found", "Run not found.");
  try {
    const next = await recordStage(sb, run, parsed.data, keyHash);
    return json({ run_id: next.id, status: next.status, stage: next.stage, stages: next.stages.map((s) => ({ id: s.id, status: s.status, verdict: s.gate?.verdict ?? null })) });
  } catch (e) {
    if (e instanceof DeliveryError) return apiError(e.status, e.code, e.message);
    return apiError(500, "stage_failed", (e as Error).message);
  }
}
