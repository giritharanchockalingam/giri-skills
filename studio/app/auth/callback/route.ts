/* Auth callback: turns a magic-link / signup-confirmation redirect into a session cookie.
 * Handles both PKCE (?code=) and token-hash links (?token_hash=&type=), then redirects to ?next. */
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { SUPABASE_URL, SUPABASE_ANON_KEY, supabaseConfigured } from "@/lib/supabase/env";

export const dynamic = "force-dynamic";

function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
}

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const next = safeNext(searchParams.get("next"));
  const fail = (reason: string) => NextResponse.redirect(new URL(`/login?next=${encodeURIComponent(next)}&auth_error=${encodeURIComponent(reason)}`, request.url));
  if (!supabaseConfigured()) return fail("Supabase is not configured.");

  const response = NextResponse.redirect(new URL(next, request.url));
  const supabase = createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (list) => { for (const { name, value, options } of list) response.cookies.set(name, value, options); },
    },
  });

  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const { error } = code
    ? await supabase.auth.exchangeCodeForSession(code)
    : tokenHash && type
      ? await supabase.auth.verifyOtp({ token_hash: tokenHash, type })
      : { error: { message: searchParams.get("error_description") ?? "Missing auth code." } };
  return error ? fail(error.message) : response;
}
