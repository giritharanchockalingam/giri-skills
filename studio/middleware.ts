/* Session refresh + route protection. Everything except /login, the consumer API (/api/v1) and MCP servers (/api/mcp), both key-authenticated,
 * the Python runtime (/api/py, secret-authenticated) and static assets requires a signed-in user. */
import { createServerClient } from "@supabase/ssr";
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
  if (!user && pathname !== "/login" && pathname !== "/auth/callback") {
    if (pathname.startsWith("/api/")) return NextResponse.json({ error: { code: "unauthenticated", message: "Sign in first." } }, { status: 401 });
    const url = new URL("/login", request.url);
    if (pathname !== "/") url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  if (user && pathname === "/login") return NextResponse.redirect(new URL("/", request.url));
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|run-worker.js|runtime/|api/v1/|api/py/|api/mcp|.*\\.(?:png|svg|ico|txt|json)$).*)"],
};
