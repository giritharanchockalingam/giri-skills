/* GET /api/delivery-runs/{id} — the run with its approvals (session member or API key of the workspace).
 * ?download=1 serves it as run.json. */
import { apiContext, apiError, json } from "@/lib/factory/http";
import { authenticateApiKey } from "@/lib/factory/apikey";
import { getDeliveryRun, getDeliveryRunByKey, listDeliveryApprovals } from "@/lib/db/delivery";
import { UUID } from "@/lib/validation";

export const dynamic = "force-dynamic";

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!UUID.test(id)) return apiError(400, "bad_request", "run id must be a UUID");
  let body: object | null = null;
  if (req.headers.get("authorization")) {
    const caller = await authenticateApiKey(req);
    if (caller instanceof Response) return caller;
    body = await getDeliveryRunByKey(caller.supabase, caller.keyHash, id);
  } else {
    const ctx = await apiContext();
    if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace, or send `Authorization: Bearer <api key>`.");
    const run = await getDeliveryRun(ctx.supabase, ctx.workspace.id, id);
    if (run) body = { ...run, approvals: await listDeliveryApprovals(ctx.supabase, run.id) };
  }
  if (!body) return apiError(404, "not_found", "Run not found.");
  const download = new URL(req.url).searchParams.get("download") === "1";
  return json(body, 200, download ? { "content-disposition": `attachment; filename="run-${id}.json"`, "cache-control": "no-store" } : { "cache-control": "no-store" });
}
