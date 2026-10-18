/* GET /api/v1/skills/{slug} — the published version's full contract (manifest without secrets; there are none in it). */
import { authenticateApiKey } from "@/lib/factory/apikey";
import { apiError, json } from "@/lib/factory/http";
import { publicContract } from "@/lib/factory/publicShape";

export const dynamic = "force-dynamic";

export async function GET(req: Request, { params }: { params: Promise<{ slug: string }> }) {
  const caller = await authenticateApiKey(req);
  if (caller instanceof Response) return caller;
  const { slug } = await params;
  const { data, error } = await caller.supabase.rpc("sf_api_skill", { p_key_hash: caller.keyHash, p_slug: slug });
  if (error) return apiError(500, "query_failed", error.message);
  if (!data) return apiError(404, "not_published", `No published version of “${slug}” is available to this key.`);
  return json(publicContract(data as Record<string, unknown>));
}
