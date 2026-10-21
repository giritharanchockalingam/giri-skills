/* Model names exactly as configured, never a made-up display name: "gpt-6-luna · OpenAI". The workspace's own
 * configured model (SF_LLM_MODEL) says so: "gpt-6-luna · OpenAI-compatible (your configured model)". SF_LLM_MODEL_LABEL
 * may add a label for it (shown beside the id, never instead of it). Pure. */
const PROVIDER: [RegExp, string][] = [[/^(gpt|o\d|text-|chatgpt)/i, "OpenAI"], [/^claude/i, "Anthropic"], [/^(llama|meta-llama)/i, "Meta"],
  [/^(gemini|gemma)/i, "Google"], [/^(mistral|mixtral|codestral)/i, "Mistral"], [/^(qwen)/i, "Alibaba"], [/^deepseek/i, "DeepSeek"]];

export const NO_MODEL = "No model (deterministic)";

export function modelLabel(id: string | null | undefined, env: Record<string, string | undefined> = process.env): string {
  if (!id || id === "dry" || id === "none") return NO_MODEL;
  const configured = env.SF_LLM_MODEL?.trim();
  if (configured && id === configured) {
    const label = env.SF_LLM_MODEL_LABEL?.trim();
    return `${id} · OpenAI-compatible (your configured model${label ? `: ${label}` : ""})`;
  }
  const provider = PROVIDER.find(([re]) => re.test(id.split("/").pop()!))?.[1];
  return provider ? `${id} · ${provider}` : id;
}
