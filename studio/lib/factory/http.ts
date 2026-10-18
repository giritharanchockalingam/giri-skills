/* Small helpers shared by the route handlers. Server only. */
import { NextResponse } from "next/server";
import { getContext, type Ctx, type WsCtx } from "./db";

export const json = (data: unknown, status = 200, headers: Record<string, string> = {}) => NextResponse.json(data, { status, headers });
export const apiError = (status: number, code: string, message: string, details?: unknown) =>
  NextResponse.json({ error: { code, message, ...(details !== undefined ? { details } : {}) } }, { status });

export async function readJson(req: Request): Promise<Record<string, unknown> | null> {
  try {
    const t = await req.text();
    if (!t) return {};
    const v = JSON.parse(t);
    return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
  } catch { return null; }
}

/** Signed-in context for UI route handlers; null (not a redirect) when signed out or without a workspace. */
export async function apiContext(): Promise<WsCtx | null> {
  let ctx: Ctx;
  try { ctx = await getContext(); } catch { return null; }
  if (!ctx.workspace || !ctx.role) return null;
  return ctx as WsCtx;
}

export const newId = () => crypto.randomUUID();
