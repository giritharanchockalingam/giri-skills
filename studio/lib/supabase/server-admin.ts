/* Service-role Supabase client. SERVER ONLY. Two callers: the GitHub webhook processor (lib/automations/process.ts),
 * which has no user session and scopes every query to the workspace that owns the verified installation; and
 * lib/factory/snapshot.ts, which writes frozen version files (a table users can read but never write). Never import
 * this from a page or component. */
import "server-only";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { SUPABASE_URL } from "./env";

/** What to tell an operator when the key is missing (kept here: the key's name appears only in this server module). */
export const ADMIN_MISSING = "the server's Supabase service key is not set (needed to process GitHub webhooks)";
export const ADMIN_FIX = "Vercel env SUPABASE_SERVICE_ROLE_KEY (Supabase → Project settings → API → service_role)";

export function adminConfigured(): boolean { return Boolean(SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY); }

export function createAdminSupabase(): SupabaseClient {
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!SUPABASE_URL || !key) throw new Error("SUPABASE_SERVICE_ROLE_KEY is not set on the server (needed to process GitHub webhooks).");
  return createClient(SUPABASE_URL, key, { auth: { persistSession: false, autoRefreshToken: false } });
}
