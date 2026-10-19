// The assistant: model client, read-only tools, the tool-calling loop and the HTTP handler. The model and the data
// are injected fakes; the tools' logic, the loop's bounds, grounding prompt, logging and limits are the real code.
import { test } from "node:test";
import assert from "node:assert/strict";
import { llmConfig, costUsd, openAiChat, LlmError, type Chat, type ChatMessage, type ToolSpec } from "../lib/assistant/llm.ts";
import { runTool, resolveRepo, TOOL_SPECS, type AssistantData, type RepoFact, type ScoreFact, type RunFact } from "../lib/assistant/tools.ts";
import { ask, systemPrompt, MAX_ROUNDS, MAX_TURNS } from "../lib/assistant/agent.ts";
import { handleAsk, HOURLY_LIMIT, type AskDeps } from "../lib/assistant/handler.ts";
import { computeInsights } from "../lib/insights/compute.ts";
import type { AssistantLogRow } from "../lib/db/assistant.ts";

/* ---------------- fixtures: a small workspace ---------------- */
const repo = (key: string, o: Partial<RepoFact> = {}): RepoFact => ({ id: `id-${key.split("/")[1]}`, key, title: key.split("/")[1], url: `https://github.com/${key}`,
  owner: null, archived: false, description: null, stack: [], lastActivity: "2026-10-19T00:00:00Z", applicable: [], ...o });
const REPOS = [
  repo("acme/billing-api", { owner: "@payments-team", stack: ["Next.js", "Supabase"], description: "Billing service" }),
  repo("acme/vg-advantage-portal", { owner: "@giri", stack: ["Next.js"] }),
  repo("acme/old-site", { archived: true }),
];
const score = (repoId: string, check_id: string, verdict: string): ScoreFact => ({ entity_id: repoId, check_id, verdict, summary: `${check_id} ${verdict}`, created_at: "2026-10-19T10:00:00Z" });
const SCORES = [score("id-billing-api", "rls", "pass"), score("id-billing-api", "nextjs", "pass"),
  score("id-vg-advantage-portal", "rls", "pass"), score("id-vg-advantage-portal", "nextjs", "fail"), score("id-vg-advantage-portal", "observability", "error")];
const RUNS: RunFact[] = [
  { automation: "Pull request gate", repo: "acme/billing-api", entity_id: "id-billing-api", event: "pull_request", pr_number: 5, head_sha: "b".repeat(40), status: "succeeded",
    verdicts: { rls: { verdict: "fail", summary: "1 error" } }, check_run_url: "https://github.com/acme/billing-api/runs/1", error: null, started_at: "2026-10-19T17:24:00Z" },
  { automation: "Keep scorecard current", repo: "acme/billing-api", entity_id: "id-billing-api", event: "push", pr_number: null, head_sha: "c".repeat(40), status: "succeeded",
    verdicts: { rls: { verdict: "pass", summary: "0 errors" } }, check_run_url: null, error: null, started_at: "2026-10-19T17:30:00Z" },
];
function data(o: Partial<AssistantData> = {}): AssistantData {
  return {
    repos: async () => REPOS, scores: async () => SCORES, automationRuns: async (n) => RUNS.slice(0, n),
    insights: async (days) => computeInsights([], [], [], days),
    route: (task) => (/dpia|data protection/i.test(task) ? [{ skill: "govern/dpia", score: 9 }, { skill: "govern/ai-transparency-notice", score: 6 }, { skill: "build/unrelated", score: 2 }] : []),
    skill: (id) => (id === "build/unrelated" ? null : { id, name: id.split("/")[1], stage: "govern", card: `Produces a ${id.split("/")[1]}` }),
    ...o,
  };
}
const call = async (name: string, args: unknown, d = data()) => runTool(name, JSON.stringify(args), d);

/* ---------------- model client ---------------- */
test("llm config: key required; defaults; prices only when both are numbers; cost never guessed", () => {
  assert.equal(llmConfig({}).ok, false);
  const c = llmConfig({ SF_LLM_API_KEY: "k", SF_LLM_BASE_URL: "https://api.openai.com/v1/", SF_LLM_MODEL: "gpt-x", SF_LLM_PRICE_IN: "0.15", SF_LLM_PRICE_OUT: "0.6" });
  assert.ok(c.ok);
  if (!c.ok) return;
  assert.equal(c.cfg.baseUrl, "https://api.openai.com/v1");
  assert.equal(costUsd(c.cfg, 1_000_000, 1_000_000), 0.75);
  assert.equal(costUsd({ priceIn: 0.15, priceOut: null }, 10, 10), null);
  const bad = llmConfig({ SF_LLM_API_KEY: "k", SF_LLM_PRICE_IN: "abc", SF_LLM_PRICE_OUT: "1" });
  assert.ok(bad.ok && bad.cfg.priceIn === null);
});

test("llm client: posts model, messages and tools with the bearer key; parses tool calls and usage", async () => {
  let seen: { url: string; init: RequestInit } | null = null;
  const fetchImpl = (async (url: string, init: RequestInit) => {
    seen = { url, init };
    return new Response(JSON.stringify({ choices: [{ message: { content: null, tool_calls: [{ id: "c1", type: "function", function: { name: "search_catalog", arguments: "{}" } }] } }],
      usage: { prompt_tokens: 120, completion_tokens: 8 } }), { status: 200 });
  }) as unknown as typeof fetch;
  const chat = openAiChat({ baseUrl: "https://m.example/v1", model: "gpt-x", key: "sk-secret", priceIn: null, priceOut: null }, fetchImpl);
  const r = await chat([{ role: "user", content: "hi" }], TOOL_SPECS);
  assert.equal(seen!.url, "https://m.example/v1/chat/completions");
  assert.equal((seen!.init.headers as Record<string, string>).Authorization, "Bearer sk-secret");
  const body = JSON.parse(String(seen!.init.body));
  assert.equal(body.model, "gpt-x");
  assert.equal(body.tools.length, TOOL_SPECS.length);
  assert.equal(body.tool_choice, "auto");
  assert.deepEqual(r.usage, { prompt: 120, completion: 8 });
  assert.equal(r.message.tool_calls![0].function.name, "search_catalog");
  await chat([{ role: "user", content: "hi" }], []);
  assert.equal("tools" in JSON.parse(String(seen!.init.body)), false, "no tools → no tools field");
});

test("llm client: provider errors become LlmError with the provider's message and any key masked; timeouts are 504", async () => {
  const cfg = { baseUrl: "https://m.example/v1", model: "m", key: "k", priceIn: null, priceOut: null };
  const e401 = openAiChat(cfg, (async () => new Response(JSON.stringify({ error: { message: "Incorrect API key provided: sk-abcdefghijk123" } }), { status: 401 })) as unknown as typeof fetch);
  await assert.rejects(e401([], []), (e: unknown) => e instanceof LlmError && e.status === 401 && /Incorrect API key/.test(e.message) && !/abcdefghijk123/.test(e.message));
  const slow = openAiChat(cfg, (async () => { const err = new Error("t"); err.name = "TimeoutError"; throw err; }) as unknown as typeof fetch);
  await assert.rejects(slow([], []), (e: unknown) => e instanceof LlmError && e.status === 504);
});

test("llm: a reasoning model that refuses tools with reasoning on is retried once with reasoning_effort none", async () => {
  const cfg = { baseUrl: "https://m.example/v1", model: "gpt-r", key: "k", priceIn: null, priceOut: null };
  const bodies: Record<string, unknown>[] = [];
  const refuse = { error: { message: "Function tools with reasoning_effort are not supported for gpt-r in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'." } };
  const ok = { choices: [{ message: { content: "done" } }], usage: { prompt_tokens: 3, completion_tokens: 1 } };
  const fetchImpl = (async (_u: string, init: RequestInit) => {
    const b = JSON.parse(String(init.body)); bodies.push(b);
    return b.reasoning_effort === "none" ? new Response(JSON.stringify(ok)) : new Response(JSON.stringify(refuse), { status: 400 });
  }) as unknown as typeof fetch;
  const r = await openAiChat(cfg, fetchImpl)([{ role: "user", content: "hi" }], TOOL_SPECS);
  assert.equal(r.message.content, "done");
  assert.equal(bodies.length, 2);
  assert.equal(bodies[0].reasoning_effort, undefined);
  assert.equal(bodies[1].reasoning_effort, "none");
  // a model that keeps refusing is not retried forever: the second 400 surfaces
  const always = openAiChat(cfg, (async () => new Response(JSON.stringify(refuse), { status: 400 })) as unknown as typeof fetch);
  await assert.rejects(always([], TOOL_SPECS), (e: unknown) => e instanceof LlmError && e.status === 400);
});

/* ---------------- tools ---------------- */
test("resolveRepo: owner/name, bare name, unique partial; otherwise candidates", () => {
  const exact = resolveRepo("acme/billing-api", REPOS);
  assert.ok("repo" in exact && exact.repo.id === "id-billing-api");
  const byName = resolveRepo("vg-advantage-portal", REPOS);
  assert.ok("repo" in byName && byName.repo.key === "acme/vg-advantage-portal");
  const partial = resolveRepo("vg advantage", REPOS);
  assert.ok("repo" in partial && partial.repo.key === "acme/vg-advantage-portal");
  const none = resolveRepo("acme", REPOS);
  assert.ok("candidates" in none && none.candidates.length === 3);
});

test("search_catalog: failing check, text query, archived excluded; each row links to its catalog page", async () => {
  const failing = await call("search_catalog", { failing_check: "nextjs" });
  assert.ok(failing.ok);
  const c = failing.content as { matched: number; total_in_catalog: number; repositories: { repository: string; link: string; scorecard: { passing_all: boolean } }[] };
  assert.deepEqual(c.repositories.map((r) => r.repository), ["acme/vg-advantage-portal"]);
  assert.equal(c.repositories[0].link, "/catalog/id-vg-advantage-portal");
  assert.equal(c.total_in_catalog, 3);
  const obs = (await call("search_catalog", { failing_check: "observability" })).content as { matched: number };
  assert.equal(obs.matched, 1, "an error verdict counts as failing");
  const q = (await call("search_catalog", { query: "payments supabase" })).content as { repositories: { repository: string; owner: string }[] };
  assert.deepEqual(q.repositories.map((r) => [r.repository, r.owner]), [["acme/billing-api", "@payments-team"]]);
  assert.equal(((await call("search_catalog", {})).content as { matched: number }).matched, 2, "archived excluded by default");
  assert.equal(((await call("search_catalog", { include_archived: true })).content as { matched: number }).matched, 3);
});

test("get_scorecard: verdicts with titles for one repository; unknown names return candidates, not a guess", async () => {
  const r = await call("get_scorecard", { repository: "vg-advantage-portal" });
  const c = r.content as { checks: { check: string; title: string; verdict: string }[]; passing_all: boolean; link: string };
  assert.equal(c.passing_all, false);
  assert.deepEqual(c.checks.map((x) => [x.check, x.verdict]), [["rls", "pass"], ["nextjs", "fail"], ["observability", "error"]]);
  assert.equal(c.checks[1].title, "Next.js conventions");
  assert.deepEqual(r.links, [{ title: "acme/vg-advantage-portal scorecard", href: "/catalog/id-vg-advantage-portal" }]);
  const unknown = await call("get_scorecard", { repository: "payroll" });
  assert.ok(unknown.ok);
  assert.match(JSON.stringify(unknown.content), /No single repository matches/);
  assert.equal((await call("get_scorecard", { repository: "old-site" })).summary, "acme/old-site: not scored");
});

test("find_skill: real matches only (relevance floor), unknown library ids dropped, nothing when nothing matches", async () => {
  const r = await call("find_skill", { task: "run a DPIA for the new feature" });
  assert.deepEqual((r.content as { matches: { skill: string }[] }).matches.map((m) => m.skill), ["govern/dpia", "govern/ai-transparency-notice"]);
  assert.deepEqual(r.links.map((l) => l.href), ["/repo/govern/dpia", "/repo/govern/ai-transparency-notice"]);
  assert.deepEqual((await call("find_skill", { task: "bake a sourdough loaf" })).content, { task: "bake a sourdough loaf", matches: [] });
});

test("list_automation_runs: filters by repository and pull request; links to the GitHub checks", async () => {
  const pr = await call("list_automation_runs", { pr_number: 5 });
  const c = pr.content as { matched: number; runs: { trigger: string; commit: string; github_check: string }[] };
  assert.equal(c.matched, 1);
  assert.equal(c.runs[0].trigger, "pull request #5");
  assert.equal(c.runs[0].commit, "bbbbbbb");
  assert.ok(pr.links.some((l) => l.href === "https://github.com/acme/billing-api/runs/1"));
  assert.equal(((await call("list_automation_runs", { repository: "billing-api" })).content as { matched: number }).matched, 2);
  assert.equal(((await call("list_automation_runs", { repository: "vg-advantage-portal" })).content as { matched: number }).matched, 0);
});

test("insights_summary: reports the period and explains hours saved; only 7/30/90 days accepted", async () => {
  const r = await call("insights_summary", { days: 7 });
  const c = r.content as { period_days: number; runs: number; note: string };
  assert.equal(c.period_days, 7);
  assert.equal(c.runs, 0);
  assert.match(c.note, /baseline/);
  assert.equal((await call("insights_summary", { days: 12 })).ok, false);
});

test("runTool: unknown tool, bad JSON, invalid arguments and data failures come back as tool errors (never throw)", async () => {
  assert.equal((await runTool("drop_table", "{}", data())).ok, false);
  assert.match(JSON.stringify((await runTool("get_scorecard", "{not json", data())).content), /not valid JSON/);
  assert.match(JSON.stringify((await runTool("get_scorecard", "{}", data())).content), /repository/);
  const broken = await runTool("search_catalog", "{}", data({ repos: async () => { throw new Error("permission denied for table"); } }));
  assert.equal(broken.ok, false);
  assert.match(JSON.stringify(broken.content), /permission denied/);
});

/* ---------------- the loop ---------------- */
type Step = { content?: string | null; calls?: [string, unknown][] };
function scripted(steps: Step[]) {
  const seen: { messages: ChatMessage[]; tools: ToolSpec[] }[] = [];
  let i = 0;
  const chat: Chat = async (messages, tools) => {
    seen.push({ messages: structuredClone(messages), tools });
    const s = steps[Math.min(i++, steps.length - 1)];
    return { message: { content: s.content ?? null, tool_calls: s.calls?.map(([name, args], k) => ({ id: `c${i}-${k}`, type: "function" as const, function: { name, arguments: JSON.stringify(args) } })) },
      usage: { prompt: 100, completion: 10 } };
  };
  return { chat, seen };
}
const CTX = { workspace: "giri-skills", today: "2026-10-19" };

test("ask: tool results go back to the model, which answers from them; evidence and usage are returned", async () => {
  const { chat, seen } = scripted([{ calls: [["search_catalog", { failing_check: "nextjs" }], ["get_scorecard", { repository: "vg-advantage-portal" }]] },
    { content: "1 repository fails: [acme/vg-advantage-portal](/catalog/id-vg-advantage-portal)." }]);
  const a = await ask([{ role: "user", content: "Which repos fail Next.js conventions?" }], CTX, chat, data());
  assert.equal(a.stopped, "answered");
  assert.equal(a.rounds, 2);
  assert.deepEqual(a.usage, { prompt: 200, completion: 20 });
  assert.deepEqual(a.evidence.map((e) => [e.tool, e.ok]), [["search_catalog", true], ["get_scorecard", true]]);
  const second = seen[1].messages;
  assert.equal(second.filter((m) => m.role === "tool").length, 2);
  assert.match((second.find((m) => m.role === "tool") as { content: string }).content, /vg-advantage-portal/);
  assert.equal(seen[0].messages[0].role, "system");
  assert.match((seen[0].messages[0] as { content: string }).content, /Answer ONLY from tool results/);
});

test("ask: bounded — after MAX_ROUNDS of lookups the model must answer without tools", async () => {
  const { chat, seen } = scripted([{ calls: [["search_catalog", {}]] }, { calls: [["search_catalog", {}]] }, { calls: [["search_catalog", {}]] },
    { calls: [["search_catalog", {}]] }, { calls: [["search_catalog", {}]] }, { content: "Here is what I found." }]);
  const a = await ask([{ role: "user", content: "loop" }], CTX, chat, data());
  assert.equal(a.stopped, "round_limit");
  assert.equal(seen.length, MAX_ROUNDS + 1);
  assert.equal(seen[MAX_ROUNDS].tools.length, 0, "final call offers no tools");
  assert.equal(a.evidence.length, MAX_ROUNDS);
  assert.equal(a.answer, "Here is what I found.");
});

test("ask: keeps only the last MAX_TURNS turns; an empty model answer is replaced with an honest line", async () => {
  const { chat, seen } = scripted([{ content: "" }]);
  const turns = Array.from({ length: MAX_TURNS + 6 }, (_, i) => ({ role: (i % 2 ? "assistant" : "user") as "user" | "assistant", content: `t${i}` }));
  turns.push({ role: "user", content: "last" });
  const a = await ask(turns, CTX, chat, data());
  assert.equal(seen[0].messages.length, MAX_TURNS + 1);
  assert.equal((seen[0].messages.at(-1) as { content: string }).content, "last");
  assert.equal(a.answer, "I could not form an answer from the workspace data.");
  assert.match(systemPrompt("ws", "2026-10-19"), /You can only read/);
});

/* ---------------- the handler ---------------- */
const CFG = { baseUrl: "https://m.example/v1", model: "gpt-x", key: "k", priceIn: 1, priceOut: 2 };
function deps(o: Partial<AskDeps> & { chatImpl?: Chat; used?: number } = {}) {
  const logs: AssistantLogRow[] = [];
  const d: AskDeps = {
    workspace: { id: "ws-1", name: "giri-skills" }, userId: "u-1",
    llm: { ok: true, cfg: CFG }, chat: () => o.chatImpl ?? scripted([{ calls: [["get_scorecard", { repository: "billing-api" }]] }, { content: "All checks pass." }]).chat,
    data: data(), questionsLastHour: async () => o.used ?? 0, log: async (r) => { logs.push(r); return null; }, now: () => 1_000, ...o,
  };
  return { d, logs };
}

test("handler: rejects malformed conversations (400) and reports a missing model setup (503) without logging", async () => {
  const { d, logs } = deps();
  assert.equal((await handleAsk({}, d)).status, 400);
  assert.equal((await handleAsk({ messages: [{ role: "assistant", content: "hi" }] }, d)).status, 400);
  assert.equal((await handleAsk({ messages: [{ role: "user", content: "x".repeat(4001) }] }, d)).status, 400);
  assert.equal((await handleAsk({ messages: [{ role: "user", content: "hi" }], extra: 1 }, d)).status, 400);
  const nc = await handleAsk({ messages: [{ role: "user", content: "hi" }] }, { ...d, llm: { ok: false, reason: "set SF_LLM_API_KEY" } });
  assert.equal(nc.status, 503);
  assert.equal(logs.length, 0);
});

test("handler: answers, logs the question with tools, tokens and cost", async () => {
  const { d, logs } = deps();
  const r = await handleAsk({ messages: [{ role: "user", content: "  Is billing-api healthy?  " }] }, d);
  assert.equal(r.status, 200);
  assert.equal(r.body.answer, "All checks pass.");
  assert.deepEqual(r.body.usage, { prompt: 200, completion: 20, cost_usd: 0.00024 });
  assert.equal(logs.length, 1);
  assert.equal(logs[0].status, "answered");
  assert.equal(logs[0].question, "Is billing-api healthy?");
  assert.deepEqual(logs[0].tools, [{ name: "get_scorecard", args: { repository: "billing-api" }, ok: true }]);
  assert.equal(logs[0].cost_usd, 0.00024);
  assert.equal(logs[0].answer_chars, "All checks pass.".length);
});

test("handler: over the hourly limit → 429, logged as limited, model not called", async () => {
  let called = false;
  const { d, logs } = deps({ used: HOURLY_LIMIT, chatImpl: async () => { called = true; return { message: { content: "x" }, usage: { prompt: 0, completion: 0 } }; } });
  const r = await handleAsk({ messages: [{ role: "user", content: "hi" }] }, d);
  assert.equal(r.status, 429);
  assert.equal(called, false);
  assert.deepEqual(logs.map((l) => l.status), ["limited"]);
});

test("handler: model failures are 502 (504 on timeout), logged as failed with the reason", async () => {
  const { d, logs } = deps({ chatImpl: async () => { throw new LlmError(401, "model error 401: bad key"); } });
  const r = await handleAsk({ messages: [{ role: "user", content: "hi" }] }, d);
  assert.equal(r.status, 502);
  assert.match(JSON.stringify(r.body), /bad key/);
  assert.equal(logs[0].status, "failed");
  assert.equal(logs[0].error, "model error 401: bad key");
  const t = deps({ chatImpl: async () => { throw new LlmError(504, "the model did not answer in time"); } });
  assert.equal((await handleAsk({ messages: [{ role: "user", content: "hi" }] }, t.d)).status, 504);
});

test("handler: an audit-log write failure still answers but says so", async () => {
  const { d } = deps({ log: async () => "permission denied" });
  const r = await handleAsk({ messages: [{ role: "user", content: "hi" }] }, d);
  assert.equal(r.status, 200);
  assert.match(String(r.body.warning), /audit log/);
});

test("tools: levels on the scorecard, below_level filter, initiatives with live progress", async () => {
  const facts = { stackIds: ["nextjs"], counts: { migrations: 0, files: 40 } };   // nextjs + observability apply
  const repos = [repo("acme/a", { facts }), repo("acme/b", { facts }), repo("acme/tools", { facts: { stackIds: ["python"], counts: { migrations: 0, files: 5 } } })];
  const scores = [score("id-a", "nextjs", "pass"), score("id-a", "observability", "pass"), score("id-b", "nextjs", "fail"), score("id-b", "observability", "pass")];
  const inis = [{ id: "i1", title: "All at Silver", description: "", target_level: "silver" as const, repos: [], owner: "Platform", due_on: "2099-01-01", status: "active" },
    { id: "i2", title: "Old", description: "", target_level: "gold" as const, repos: [], owner: "x", due_on: "2020-01-01", status: "closed" }];
  const d = data({ repos: async () => repos, scores: async () => scores, initiatives: async () => inis });

  const card = await call("get_scorecard", { repository: "b" }, d);
  const c = card.content as { level: string; next_level: { level: string; blocked_by: string[] } };
  assert.equal(c.level, "Bronze");
  assert.deepEqual(c.next_level.blocked_by, ["Next.js conventions: fails"]);

  const below = await call("search_catalog", { below_level: "silver" }, d);
  assert.deepEqual((below.content as { repositories: { repository: string }[] }).repositories.map((r) => r.repository), ["acme/b"], "acme/tools has no level, acme/a is Gold");

  const ini = await call("list_initiatives", {}, d);
  const rows = (ini.content as { initiatives: { title: string; progress: string; repositories: { repository: string; meets_target: boolean }[] }[] }).initiatives;
  assert.deepEqual(rows.map((r) => [r.title, r.progress]), [["All at Silver", "1 of 2 repositories (50%)"]], "closed initiatives hidden by default");
  assert.deepEqual(rows[0].repositories.map((r) => [r.repository, r.meets_target]), [["acme/b", false], ["acme/a", true]]);
  assert.equal(((await call("list_initiatives", { include_closed: true }, d)).content as { initiatives: unknown[] }).initiatives.length, 2);
});
