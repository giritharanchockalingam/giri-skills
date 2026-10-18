/* GET /api/v1/runs/{id} — a run's status and result (logs excluded), scoped to the key's workspace. */
import { authenticateApiKey } from "@/lib/factory/apikey";
import { stripRuntimePaths, publicContract } from "@/lib/factory/publicShape";
import { apiError, json } from "@/lib/factory/http";

export const dynamic = "force-dynamic";

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const caller = await authenticateApiKey(req);
  if (caller instanceof Response) return caller;
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/.test(id)) return apiError(400, "bad_request", "Run id must be a UUID.");
  const { data, error } = await caller.supabase.rpc("sf_api_run_get", { p_key_hash: caller.keyHash, p_run: id });
  if (error) return apiError(500, "query_failed", error.message);
  if (!data) return apiError(404, "not_found", "No such run for this key's workspace.");
  return json(stripRuntimePaths(publicContract(data as Record<string, unknown>)));
}
