/* POST /api/v1/uses — an agent (the governed Claude Code plugin's hook) reports one load of a skill:
 * {slug, version, sha256, event: loaded|blocked, integrity: verified|modified|unknown, session?}.
 * The factory records it with whether that version is still the current published one. */
import { authenticateApiKey } from "@/lib/factory/apikey";
import { apiError, json, readJson } from "@/lib/factory/http";
import { parseUse } from "@/lib/factory/uses";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const caller = await authenticateApiKey(req);
  if (caller instanceof Response) return caller;
  const body = await readJson(req);
  if (!body) return apiError(400, "bad_json", "Send a JSON object.");
  const use = parseUse(body);
  if (typeof use === "string") return apiError(400, "bad_request", use);
  const { data, error } = await caller.supabase.rpc("sf_record_use", {
    p_key_hash: caller.keyHash, p_slug: use.slug, p_version: use.version, p_sha256: use.sha256 ?? "",
    p_event: use.event, p_integrity: use.integrity, p_session: use.session ?? null,
  });
  if (error) return apiError(/unknown (skill|version)/.test(error.message) ? 404 : 500, "record_failed", error.message);
  return json(data, 201);
}
