/* The assistant: questions over the workspace's catalog, scorecards, automations, insights and skills library.
 * Signed-in members only; every read runs under their own session (RLS). Logic in lib/assistant (unit-tested). */
import { NextResponse } from "next/server";
import { apiContext, readJson, apiError } from "@/lib/factory/http";
import { handleAsk } from "@/lib/assistant/handler";
import { llmConfig, openAiChat } from "@/lib/assistant/llm";
import { assistantData, logQuestion, questionsLastHour } from "@/lib/db/assistant";
import { log } from "@/lib/logger";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST(req: Request) {
  const origin = req.headers.get("origin");
  if (origin && new URL(origin).host !== new URL(req.url).host) return apiError(403, "forbidden", "cross-site request");
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthorized", "Sign in and choose a workspace.");
  const body = await readJson(req);
  if (body === null) return apiError(400, "bad_request", "body must be a JSON object");
  const sb = ctx.supabase, ws = ctx.workspace.id, userId = ctx.user.id;
  const r = await handleAsk(body, {
    workspace: { id: ws, name: ctx.workspace.name }, userId,
    llm: llmConfig(), chat: (cfg) => openAiChat(cfg),
    data: assistantData(sb, ws),
    questionsLastHour: () => questionsLastHour(sb, ws, userId),
    log: async (row) => {
      const e = await logQuestion(sb, row);
      if (e) log.error({ action: "assistant.log", err: e }, "could not record assistant question");
      return e;
    },
  });
  if (r.status >= 500) log.warn({ action: "assistant.ask", status: r.status, error: r.body.error }, "assistant question failed");
  return NextResponse.json(r.body, { status: r.status, headers: { "Cache-Control": "no-store" } });
}
