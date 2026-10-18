import { createServerClient } from "@supabase/ssr";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import { SUPABASE_URL, SUPABASE_ANON_KEY, supabaseConfigured, SETUP_MESSAGE } from "./env";

/** Per-request client bound to the signed-in user's session cookies (RLS applies as that user). */
export async function createServerSupabase(): Promise<SupabaseClient> {
  if (!supabaseConfigured()) throw new Error(SETUP_MESSAGE);
  const store = await cookies();
  return createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll: () => store.getAll(),
      setAll: (list) => {
        try { for (const { name, value, options } of list) store.set(name, value, options); } catch { /* read-only context (server component): middleware refreshes the session */ }
      },
    },
  });
}

/** Anonymous client for the consumer API: no session, only SECURITY DEFINER RPCs that verify the API key hash. */
export function createAnonSupabase(): SupabaseClient {
  if (!supabaseConfigured()) throw new Error(SETUP_MESSAGE);
  return createClient(SUPABASE_URL, SUPABASE_ANON_KEY, { auth: { persistSession: false, autoRefreshToken: false } });
}
