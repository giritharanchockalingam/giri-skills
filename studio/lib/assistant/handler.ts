/* POST /api/assistant, independent of Next: validate the conversation, apply the hourly limit, ask, and log every
 * question (answered, failed or limited). Returns status + JSON body; the route only wires the real dependencies. */
import { z } from "zod";
import { ask, MAX_TURNS, type AssistantAnswer } from "./agent";
import { costUsd, LlmError, type Chat, type LlmConfig } from "./llm";
import type { AssistantData } from "./tools";
import type { AssistantLogRow } from "@/lib/db/assistant";

export const HOURLY_LIMIT = 60;
export const AskBody = z.object({
  messages: z.array(z.object({ role: z.enum(["user", "assistant"]), content: z.string().trim().min(1).max(4000) })).min(1).max(40)
    .refine((m) => m[m.length - 1].role === "user", "the last message must be the question"),
}).strict();

export interface AskDeps {
  workspace: { id: string; name: string };
  userId: string;
  llm: { ok: true; cfg: LlmConfig } | { ok: false; reason: string };
  chat: (cfg: LlmConfig) => Chat;
  data: AssistantData;
  questionsLastHour: () => Promise<number>;
  log: (row: AssistantLogRow) => Promise<string | null>;
  now?: () => number;
}
export interface Reply { status: number; body: Record<string, unknown> }
const err = (status: number, code: string, message: string): Reply => ({ status, body: { error: { code, message } } });

export async function handleAsk(raw: unknown, d: AskDeps): Promise<Reply> {
  const parsed = AskBody.safeParse(raw);
  if (!parsed.success) return err(400, "bad_request", parsed.error.issues.map((i) => `${i.path.join(".") || "body"}: ${i.message}`).join("; "));
  const turns = parsed.data.messages.slice(-MAX_TURNS);
  const question = turns[turns.length - 1].content;
  if (!d.llm.ok) return err(503, "not_configured", d.llm.reason);
  const cfg = d.llm.cfg;
  const now = d.now ?? Date.now;
  const base = { workspace_id: d.workspace.id, user_id: d.userId, question, model: cfg.model };

  if ((await d.questionsLastHour()) >= HOURLY_LIMIT) {
    await d.log({ ...base, answer_chars: 0, tools: [], prompt_tokens: 0, completion_tokens: 0, cost_usd: null, status: "limited", error: null, duration_ms: 0 });
    return err(429, "rate_limited", `You have asked ${HOURLY_LIMIT} questions in the last hour; try again shortly.`);
  }

  const started = now();
  let a: AssistantAnswer;
  try {
    a = await ask(turns, { workspace: d.workspace.name, today: new Date(started).toISOString().slice(0, 10) }, d.chat(cfg), d.data);
  } catch (e) {
    const message = e instanceof LlmError ? e.message : `the assistant failed: ${(e as Error).message}`;
    await d.log({ ...base, answer_chars: 0, tools: [], prompt_tokens: 0, completion_tokens: 0, cost_usd: null, status: "failed", error: message.slice(0, 500), duration_ms: now() - started });
    return err(e instanceof LlmError && e.status === 504 ? 504 : 502, "model_failed", message);
  }
  const cost = costUsd(cfg, a.usage.prompt, a.usage.completion);
  const logErr = await d.log({ ...base, answer_chars: a.answer.length, tools: a.evidence.map((e) => ({ name: e.tool, args: e.args, ok: e.ok })),
    prompt_tokens: a.usage.prompt, completion_tokens: a.usage.completion, cost_usd: cost, status: "answered", error: null, duration_ms: now() - started });
  return { status: 200, body: { answer: a.answer, evidence: a.evidence, usage: { ...a.usage, cost_usd: cost }, model: cfg.model, rounds: a.rounds,
    ...(a.stopped === "round_limit" ? { note: "Stopped after the maximum number of lookups; the answer uses what was found." } : {}),
    ...(logErr ? { warning: "The question could not be recorded in the audit log." } : {}) } };
}
