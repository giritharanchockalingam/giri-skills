// Fictional fixture (ui-component-quality evals): Next.js middleware — imports next/server, no JSX; must NOT be scanned.
import { NextResponse } from "next/server";

export function middleware(request) {
  const res = NextResponse.next();
  res.headers.set("x-frame-options", "DENY");
  return res;
}

export const config = { matcher: ["/((?!_next|api/health).*)"] };
