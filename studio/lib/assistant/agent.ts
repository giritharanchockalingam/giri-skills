/* The assistant loop: the model may call the read-only tools (several rounds, bounded), then answers from what they
 * returned. Pure — the model (Chat) and the data (AssistantData) are injected, so every path is unit-tested.
 * Grounding rules live in the system prompt; the evidence the answer rests on is returned to the person verbatim. */
import type { Chat, ChatMessage } from "./llm";
import { TOOL_SPECS, runTool, type AssistantData, type Link } from "./tools";

export const MAX_ROUNDS = 5;
export const MAX_TURNS = 12;

export interface Turn { role: "user" | "assistant"; content: string }
export interface Evidence { tool: string; args: unknown; ok: boolean; summary: string; links: Link[] }
export interface AssistantAnswer { answer: string; evidence: Evidence[]; usage: { prompt: number; completion: number }; rounds: number; stopped: "answered" | "round_limit" }

export function systemPrompt(workspace: string, today: string): string {
  return [
    `You are the Skills Factory assistant for the workspace "${workspace}". Today is ${today}.`,
    "You answer questions about this workspace's software catalog (repositories, owners, stacks), scorecards (the latest verdict of each check on each repository's default branch, and the Bronze/Silver/Gold level that follows from them), initiatives (a level set as a goal with an owner and a deadline), delivery metrics from GitHub (DORA-style: deploy frequency, lead time, change-failure proxy), workflow automations and their runs (pull-request gates and default-branch updates), usage and value (Insights), and the skills library.",
    "Rules:",
    "1. Use the tools for every fact. Answer ONLY from tool results in this conversation. Never invent repositories, owners, numbers, verdicts, dates or links.",
    "2. If the tools return nothing that answers the question, say plainly that the workspace data does not show it, and say which tool or page would (e.g. the repository is not in the catalog yet).",
    "3. Link records with the markdown links the tools give (the `link` fields, e.g. [owner/repo](/catalog/…)). Do not make up URLs.",
    "4. Hours saved are estimates from admin-set baselines; say so when you quote them, with the baseline owner when it is an estimate. No dollar values unless a tool returns one.",
    "5. Be concise: lead with the answer in one or two sentences, then a short table or list when there are several items. No preamble.",
    "6. You can only read. If asked to change something (run a check, create an automation, merge), say which page does it and do not claim it was done.",
  ].join("\n");
}

export async function ask(turns: Turn[], ctx: { workspace: string; today: string }, chat: Chat, data: AssistantData): Promise<AssistantAnswer> {
  const messages: ChatMessage[] = [{ role: "system", content: systemPrompt(ctx.workspace, ctx.today) }, ...turns.slice(-MAX_TURNS).map((t) => ({ role: t.role, content: t.content }))];
  const evidence: Evidence[] = [];
  const usage = { prompt: 0, completion: 0 };
  for (let round = 1; round <= MAX_ROUNDS + 1; round++) {
    const last = round > MAX_ROUNDS;                       // final round: no tools, answer from what was gathered
    const reply = await chat(messages, last ? [] : TOOL_SPECS);
    usage.prompt += reply.usage.prompt; usage.completion += reply.usage.completion;
    const calls = last ? [] : reply.message.tool_calls ?? [];
    if (!calls.length) {
      const answer = (reply.message.content ?? "").trim() || "I could not form an answer from the workspace data.";
      return { answer, evidence, usage, rounds: round, stopped: last ? "round_limit" : "answered" };
    }
    messages.push({ role: "assistant", content: reply.message.content, tool_calls: calls });
    for (const c of calls) {
      const r = await runTool(c.function.name, c.function.arguments, data);
      evidence.push({ tool: c.function.name, args: r.args, ok: r.ok, summary: r.summary, links: r.links });
      messages.push({ role: "tool", tool_call_id: c.id, content: JSON.stringify(r.content).slice(0, 24_000) });
    }
  }
  /* c8 ignore next */
  throw new Error("unreachable");
}
