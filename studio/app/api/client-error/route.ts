/* Browser exceptions caught by the error boundaries, recorded in the server log so they can be diagnosed (the
 * browser console is not visible to us). Bounded, redacted, no PII: message, digest, path and a short stack only. */
import { NextResponse } from "next/server";
import { log } from "@/lib/logger";

const clip = (v: unknown, n: number) => (typeof v === "string" ? v.slice(0, n) : undefined);

export async function POST(req: Request) {
  let body: Record<string, unknown> = {};
  try { body = JSON.parse((await req.text()).slice(0, 8_000)); } catch { return NextResponse.json({ ok: false }, { status: 400 }); }
  log.error({ action: "client.exception", message: clip(body.message, 500), digest: clip(body.digest, 100), path: clip(body.path, 300), stack: clip(body.stack, 2_000), ua: clip(req.headers.get("user-agent"), 200) }, "browser exception");
  return NextResponse.json({ ok: true });
}
