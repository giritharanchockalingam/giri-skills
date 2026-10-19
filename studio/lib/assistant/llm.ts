/* The assistant's model: any OpenAI-compatible chat-completions endpoint with tool calling (SF_LLM_*). The key is read
 * from the environment on the server and never logged or returned. */
import { DEFAULT_COMPAT_BASE_URL, DEFAULT_COMPAT_MODEL } from "@/lib/factory/providers";

export interface ToolCall { id: string; type: "function"; function: { name: string; arguments: string } }
export type ChatMessage =
  | { role: "system" | "user"; content: string }
  | { role: "assistant"; content: string | null; tool_calls?: ToolCall[] }
  | { role: "tool"; tool_call_id: string; content: string };
export interface ToolSpec { type: "function"; function: { name: string; description: string; parameters: Record<string, unknown> } }
export interface ChatReply { message: { content: string | null; tool_calls?: ToolCall[] }; usage: { prompt: number; completion: number } }
export type Chat = (messages: ChatMessage[], tools: ToolSpec[]) => Promise<ChatReply>;

export interface LlmConfig { baseUrl: string; model: string; key: string; priceIn: number | null; priceOut: number | null }
export function llmConfig(env: Record<string, string | undefined> = process.env): { ok: true; cfg: LlmConfig } | { ok: false; reason: string } {
  const key = env.SF_LLM_API_KEY?.trim();
  if (!key) return { ok: false, reason: "The assistant needs a model: set SF_LLM_API_KEY (and SF_LLM_BASE_URL / SF_LLM_MODEL) in Vercel and redeploy." };
  const num = (v?: string) => (v && Number.isFinite(Number(v)) && Number(v) >= 0 ? Number(v) : null);
  return { ok: true, cfg: { key, baseUrl: (env.SF_LLM_BASE_URL?.trim() || DEFAULT_COMPAT_BASE_URL).replace(/\/+$/, ""),
    model: env.SF_LLM_MODEL?.trim() || DEFAULT_COMPAT_MODEL, priceIn: num(env.SF_LLM_PRICE_IN), priceOut: num(env.SF_LLM_PRICE_OUT) } };
}

/** USD for the tokens used, when the deployment sets prices (per 1M tokens); otherwise null — never guessed. */
export const costUsd = (cfg: Pick<LlmConfig, "priceIn" | "priceOut">, prompt: number, completion: number) =>
  cfg.priceIn == null || cfg.priceOut == null ? null : Math.round(((prompt * cfg.priceIn + completion * cfg.priceOut) / 1e6) * 1e6) / 1e6;

export class LlmError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.name = "LlmError"; this.status = status; }
}

export function openAiChat(cfg: LlmConfig, fetchImpl: typeof fetch = fetch, timeoutMs = 45_000): Chat {
  return async (messages, tools) => {
    let res: Response;
    try {
      res = await fetchImpl(`${cfg.baseUrl}/chat/completions`, {
        method: "POST", signal: AbortSignal.timeout(timeoutMs),
        headers: { Authorization: `Bearer ${cfg.key}`, "Content-Type": "application/json" },
        body: JSON.stringify({ model: cfg.model, messages, ...(tools.length ? { tools, tool_choice: "auto" } : {}) }),
      });
    } catch (e) {
      throw new LlmError(504, (e as Error).name === "TimeoutError" ? "the model did not answer in time" : `could not reach the model: ${(e as Error).message}`);
    }
    const text = await res.text();
    if (!res.ok) {
      let msg = text.slice(0, 300);
      try { msg = (JSON.parse(text) as { error?: { message?: string } }).error?.message ?? msg; } catch { /* keep the raw text */ }
      throw new LlmError(res.status, `model error ${res.status}: ${msg.replace(/sk-[A-Za-z0-9_-]{8,}/g, "sk-…")}`);
    }
    const j = JSON.parse(text) as { choices?: { message?: ChatReply["message"] }[]; usage?: { prompt_tokens?: number; completion_tokens?: number } };
    const message = j.choices?.[0]?.message;
    if (!message) throw new LlmError(502, "the model returned no message");
    return { message: { content: message.content ?? null, tool_calls: message.tool_calls?.length ? message.tool_calls : undefined },
      usage: { prompt: j.usage?.prompt_tokens ?? 0, completion: j.usage?.completion_tokens ?? 0 } };
  };
}
