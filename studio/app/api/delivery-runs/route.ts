/* POST /api/delivery-runs — start a delivery run: {pipeline, repo, ref?, request, executor?} → {run_id, status, command, notice}.
 * The database checks sf_pipeline_access for the caller's job roles (admins always) and audits delivery.start; the
 * executor is dispatched (GitHub Actions) or the exact IDE command is returned. GET lists the workspace's runs. */
import { apiContext, apiError, json, readJson } from "@/lib/factory/http";
import { DeliveryStartInput } from "@/lib/validation";
import { DeliveryError, startForSession } from "@/lib/delivery/server";
import { listDeliveryRuns } from "@/lib/db/delivery";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  const body = await readJson(req);
  if (!body) return apiError(400, "bad_request", "Body must be a JSON object.");
  const parsed = DeliveryStartInput.safeParse(body);
  if (!parsed.success) return apiError(400, "invalid_inputs", "Some inputs are missing or invalid.", parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`));
  try {
    const r = await startForSession(ctx, parsed.data, new URL(req.url).origin);
    return json({ run_id: r.run.id, status: r.run.status, executor: r.run.executor, executor_ref: r.run.executor_ref, command: r.command, notice: r.notice }, 201);
  } catch (e) {
    if (e instanceof DeliveryError) return apiError(e.status, e.code, e.message);
    return apiError(500, "delivery_failed", (e as Error).message);
  }
}

export async function GET() {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  const runs = await listDeliveryRuns(ctx.supabase, ctx.workspace.id);
  return json({ runs: runs.map((r) => ({ id: r.id, pipeline: r.pipeline, repo: r.repo, ref: r.ref, status: r.status, stage: r.stage, executor: r.executor, pr: r.pr, created_at: r.created_at, updated_at: r.updated_at })) });
}
