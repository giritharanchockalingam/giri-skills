/* GET /api/v1/skills/{slug}/snapshot — the published version's frozen files (the exact files it was reviewed and
 * approved on) and their hash. Used by scripts/build_plugin.py to build the governed Claude Code plugin. 404 when the
 * skill is not published, has no frozen files, or this key may not run it. */
import { authenticateApiKey } from "@/lib/factory/apikey";
import { apiError, json } from "@/lib/factory/http";

export const dynamic = "force-dynamic";

export async function GET(req: Request, { params }: { params: Promise<{ slug: string }> }) {
  const caller = await authenticateApiKey(req);
  if (caller instanceof Response) return caller;
  const { slug } = await params;
  if (!/^[a-z0-9-]{1,80}$/.test(slug)) return apiError(400, "bad_slug", "A skill slug is lowercase letters, digits and dashes.");
  const { data, error } = await caller.supabase.rpc("sf_api_skill_snapshot", { p_key_hash: caller.keyHash, p_slug: slug });
  if (error) return apiError(500, "query_failed", error.message);
  if (!data) return apiError(404, "not_available", `No published, frozen version of “${slug}” is available to this key.`);
  return json(data);
}
