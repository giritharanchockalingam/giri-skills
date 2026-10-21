/* Auth callback: turns a magic-link / signup-confirmation redirect into a session cookie.
 * Handles both PKCE (?code=) and token-hash links (?token_hash=&type=), then redirects to ?next. */
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { SUPABASE_URL, SUPABASE_ANON_KEY, supabaseConfigured } from "@/lib/supabase/env";
import { classifyAuthError } from "@/lib/authError";
import { log } from "@/lib/logger";

export const dynamic = "force-dynamic";

function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
}

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const next = safeNext(searchParams.get("next"));
  // the raw provider message is logged here and never shown; the sign-in page shows a friendly message for the class
  const fail = (reason: string) => {
    const kind = classifyAuthError(reason);
    log.warn({ action: "auth.callback_failed", kind, reason: reason.slice(0, 500) }, "sign-in link did not complete");
    return NextResponse.redirect(new URL(`/login?next=${encodeURIComponent(next)}&auth_error=${kind}`, request.url));
  };
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
  if (error) return fail(error.message);
  await supabase.rpc("sf_accept_invitations");   // pending invitations for this email become memberships (no-op otherwise)
  return response;
}
