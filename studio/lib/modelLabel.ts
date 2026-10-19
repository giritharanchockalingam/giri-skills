/* Model names for people: "gpt-6-luna" → "GPT-6 Luna (OpenAI)". The exact model id stays visible on hover and wherever
 * an id matters (admin, run records). SF_LLM_MODEL_LABEL overrides the label of the configured model. Pure. */
const PROVIDER: [RegExp, string][] = [[/^(gpt|o\d|text-|chatgpt)/i, "OpenAI"], [/^claude/i, "Anthropic"], [/^(llama|meta-llama)/i, "Meta"],
  [/^(gemini|gemma)/i, "Google"], [/^(mistral|mixtral|codestral)/i, "Mistral"], [/^(qwen)/i, "Alibaba"], [/^deepseek/i, "DeepSeek"]];
const word = (w: string) => (/^(gpt|ai|llm|o\d)$/i.test(w) ? w.toUpperCase() : /^\d/.test(w) ? w : w[0].toUpperCase() + w.slice(1));

export function modelLabel(id: string | null | undefined, env: Record<string, string | undefined> = process.env): string {
  if (!id) return "no model";
  if (id === "dry" || id === "none") return "no model (deterministic steps only)";
  const override = env.SF_LLM_MODEL_LABEL?.trim();
  if (override && id === env.SF_LLM_MODEL?.trim()) return override;
  const base = id.split("/").pop()!;
  const provider = PROVIDER.find(([re]) => re.test(base))?.[1];
  // "gpt-6-luna" → GPT-6 Luna; "gpt-4.1-mini" → GPT-4.1 Mini; "claude-sonnet-4-5" → Claude Sonnet 4.5
  const parts = base.split("-");
  const name = parts[0].toLowerCase() === "gpt" && parts[1] ? [`GPT-${parts[1]}`, ...parts.slice(2).map(word)].join(" ")
    : parts.map(word).join(" ").replace(/(\d) (\d)\b/g, "$1.$2");
  return provider ? `${name} (${provider})` : name;
}
