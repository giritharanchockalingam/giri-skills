/* Session refresh + route protection. Everything except /login, /start (public, static copy), the consumer API (/api/v1) and MCP servers (/api/mcp), both key-authenticated, health checks (/api/health, deep check bearer-protected), the Port webhook and operator routes (/api/port/actions signed; /api/port/sync and /api/port/reconcile bearer-protected),
 * the Python runtime (/api/py, secret-authenticated) and static assets requires a signed-in user. */
import { createServerClient } from "@supabase/ssr";
import { isKeyBearingDeliveryRequest } from "@/lib/delivery/auth";
import { NextResponse, type NextRequest } from "next/server";
import { SUPABASE_URL, SUPABASE_ANON_KEY, supabaseConfigured } from "@/lib/supabase/env";

export async function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname.replace(/\/+$/, "") || "/";  // tolerate "/login/" links
  if (!supabaseConfigured()) {
    // honest setup state: the login page explains what is missing
    return pathname === "/login" ? NextResponse.next() : NextResponse.redirect(new URL("/login?setup=1", request.url));
  }
  let response = NextResponse.next({ request });
  const supabase = createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (list) => {
        for (const { name, value } of list) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of list) response.cookies.set(name, value, options);
      },
    },
  });
  const { data: { user } } = await supabase.auth.getUser();
  // the delivery executor (scripts/deliver.py, GitHub Actions) calls back with an API key, not a session: those routes
  // authenticate the key themselves (lib/factory/apikey), so a key-bearing request passes through
  const keyBearing = isKeyBearingDeliveryRequest(pathname, request.headers.get("authorization"));
  if (!user && !keyBearing && pathname !== "/login" && pathname !== "/auth/callback" && pathname !== "/start") {   // /start: the public "how it fits together" page
    if (pathname.startsWith("/api/")) return NextResponse.json({ error: { code: "unauthenticated", message: "Sign in first." } }, { status: 401 });
    const url = new URL("/login", request.url);
    if (pathname !== "/") url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  if (user && pathname === "/login") return NextResponse.redirect(new URL("/", request.url));
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|run-worker.js|runtime/|api/v1/|api/py/|api/mcp|api/health|api/github/webhook|api/port/actions|api/port/sync|api/port/reconcile|.*\\.(?:png|svg|ico|txt|json)$).*)"],
};
