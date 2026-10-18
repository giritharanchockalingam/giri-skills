/* Model providers the runtime can call. Keys live only in the deployment environment (never in the DB or UI).
 *  anthropic      ANTHROPIC_API_KEY
 *  openai_compat  SF_LLM_API_KEY + SF_LLM_BASE_URL (default Groq: https://api.groq.com/openai/v1) — any OpenAI-compatible
 *                 chat-completions endpoint (Groq free tier, OpenRouter, a self-hosted vLLM/Ollama gateway, …) */
export const PROVIDERS = ["none", "anthropic", "openai_compat"] as const;
export type ProviderName = (typeof PROVIDERS)[number];
export const DEFAULT_COMPAT_BASE_URL = "https://api.groq.com/openai/v1";
export const DEFAULT_COMPAT_MODEL = "llama-3.3-70b-versatile";

export const PROVIDER_LABEL: Record<ProviderName, string> = {
  none: "none — scripts only",
  anthropic: "anthropic (paid)",
  openai_compat: "OpenAI-compatible (e.g. Groq free tier)",
};

const ENV_KEY: Record<Exclude<ProviderName, "none">, string> = { anthropic: "ANTHROPIC_API_KEY", openai_compat: "SF_LLM_API_KEY" };

/** Server only. */
export function providerKeyPresent(p: string): boolean {
  if (p === "none") return true;
  const k = ENV_KEY[p as keyof typeof ENV_KEY];
  return Boolean(k && process.env[k]);
}
export const providerEnvKey = (p: string) => ENV_KEY[p as keyof typeof ENV_KEY] ?? null;

/** Which provider newly imported skills with llm steps should use: the one whose key is configured, preferring the free one. */
export function defaultLlmProvider(): { provider: ProviderName; model: string | null } {
  if (process.env.SF_LLM_API_KEY) return { provider: "openai_compat", model: process.env.SF_LLM_MODEL || DEFAULT_COMPAT_MODEL };
  return { provider: "anthropic", model: null };
}
