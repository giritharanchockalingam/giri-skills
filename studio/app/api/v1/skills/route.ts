/* GET /api/v1/skills — published skills visible to this API key's workspace, with their input/output contracts. */
import { authenticateApiKey } from "@/lib/factory/apikey";
import { apiError, json } from "@/lib/factory/http";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const caller = await authenticateApiKey(req);
  if (caller instanceof Response) return caller;
  const { data, error } = await caller.supabase.rpc("sf_api_skills", { p_key_hash: caller.keyHash });
  if (error) return apiError(500, "query_failed", error.message);
  return json({ skills: data ?? [] });
}
