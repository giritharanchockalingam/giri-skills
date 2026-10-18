/* Consumer-API authentication: `Authorization: Bearer sf_live_…` → sha256 → sf_resolve_api_key (SECURITY DEFINER, anon role).
 * Nothing on this path uses a user session; every read/write goes through the sf_api_* RPCs that re-verify the hash. */
import { createAnonSupabase } from "@/lib/supabase/server";
import { apiKeyHash, looksLikeApiKey } from "./hash";
import { apiError } from "./http";

export interface ApiCaller { supabase: ReturnType<typeof createAnonSupabase>; keyHash: string; apiKeyId: string; workspaceId: string }

export async function authenticateApiKey(req: Request): Promise<ApiCaller | Response> {
  const auth = req.headers.get("authorization") ?? "";
  const m = auth.match(/^Bearer\s+(\S+)$/i);
  if (!m) return apiError(401, "unauthenticated", "Send `Authorization: Bearer <api key>`.");
  if (!looksLikeApiKey(m[1])) return apiError(401, "invalid_key", "That is not a factory API key (keys start with sf_live_).");
  const keyHash = apiKeyHash(m[1]);
  let supabase;
  try { supabase = createAnonSupabase(); } catch (e) { return apiError(503, "not_configured", (e as Error).message); }
  const { data, error } = await supabase.rpc("sf_resolve_api_key", { p_key_hash: keyHash });
  if (error) return apiError(500, "auth_failed", error.message);
  const row = Array.isArray(data) ? data[0] : data;
  if (!row) return apiError(401, "invalid_key", "Unknown or revoked API key.");
  return { supabase, keyHash, apiKeyId: row.api_key_id, workspaceId: row.workspace_id };
}
