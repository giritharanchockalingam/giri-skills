/* Supabase connection settings. Both values are public (the anon key is designed to ship to browsers; RLS does the
 * protection). Missing values are reported as a setup state, never worked around. */
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";
export const supabaseConfigured = () => Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
export const SETUP_MESSAGE = "Supabase is not configured: set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.";
