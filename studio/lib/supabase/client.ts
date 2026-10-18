"use client";
import { createBrowserClient } from "@supabase/ssr";
import { SUPABASE_URL, SUPABASE_ANON_KEY } from "./env";

let client: ReturnType<typeof createBrowserClient> | null = null;
export function createBrowserSupabase() {
  return (client ??= createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY));
}
