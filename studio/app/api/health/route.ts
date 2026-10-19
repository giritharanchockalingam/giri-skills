// app/api/health/route.ts — liveness. No dependencies. Never cached.
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET() {
  return NextResponse.json(
    {
      status: "ok",
      version: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "local",
      env: process.env.VERCEL_ENV ?? process.env.NODE_ENV ?? "development",
      ts: new Date().toISOString(),
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
