/* The assistant's tools: read-only questions over the workspace's own records (catalog, scorecards, automation runs,
 * insights, the skills library). Pure: each tool reads through the AssistantData port (the route backs it with the
 * signed-in user's RLS-scoped client) and returns compact JSON for the model plus evidence links for the person.
 * Nothing here writes, and every result carries the portal link of the record it came from. */
import { z } from "zod";
import type { ToolSpec } from "./llm";
import type { Insights } from "@/lib/insights/compute";
import type { EntityFacts } from "@/lib/scorecards/checks";
import { levelOf, atLeast, LEVEL_LABEL, LEVEL_RULE, type Level } from "@/lib/scorecards/levels";
import { progressOf, initiativeState } from "@/lib/scorecards/initiatives";

export interface RepoFact { id: string; key: string; title: string; url: string; owner: string | null; archived: boolean; description: string | null;
  stack: string[]; lastActivity: string | null; applicable: { skill: string; why: string }[];
  /** Stack ids and file counts: which checks apply, hence the repository's scorecard level. */
  facts?: EntityFacts;
  /** Agents, MCP servers, skills, MCP configs and agent instructions found in the repository (with evidence). */
  aiAssets?: { kind: string; name: string; path: string; detail: string; evidence: string[] }[] }
export interface ScoreFact { entity_id: string; check_id: string; verdict: string; summary: string; created_at: string }
export interface RunFact { automation: string; repo: string; entity_id: string | null; event: string; pr_number: number | null; head_sha: string | null; status: string;
  verdicts: Record<string, { verdict: string; summary: string }>; check_run_url: string | null; error: string | null; started_at: string }
export interface SkillFact { id: string; name: string; stage: string | null; card: string }
export interface InitiativeFact { id: string; title: string; description: string; target_level: Level; repos: string[]; owner: string; due_on: string; status: string; created_at?: string }

export interface AssistantData {
  repos(): Promise<RepoFact[]>;
  scores(): Promise<ScoreFact[]>;
  automationRuns(limit: number): Promise<RunFact[]>;
  insights(days: number): Promise<Insights>;
  route(task: string, k: number): { skill: string; score: number }[];
  skill(id: string): SkillFact | null;
  initiatives?(): Promise<InitiativeFact[]>;
  entities?(): Promise<{ id: string; kind: string; source: string; key: string; title: string; url: string; properties: Record<string, unknown> }[]>;
  relations?(): Promise<{ from: string; to: string; type: string; evidence: string }[]>;
  delivery?(): Promise<{ entity_id: string; key: string; computed_at: string; notes: string[]; d30: unknown; d90: unknown }[]>;
}

export interface Link { title: string; href: string }
export interface ToolResult { content: unknown; links: Link[]; summary: string }
interface ToolDef<S extends z.ZodTypeAny> { spec: ToolSpec; schema: S; run: (args: z.infer<S>, d: AssistantData) => Promise<ToolResult> }
/** Infers each tool's argument type from its zod schema. */
const tool = <S extends z.ZodTypeAny>(t: ToolDef<S>) => t as unknown as ToolDef<z.ZodTypeAny>;

export const CHECK_TITLES: Record<string, string> = {
  rls: "Database security (row-level security)", tenancy: "Tenant isolation", nextjs: "Next.js conventions", observability: "Observability (logging, health, alerts)",
};
/** Same relevance floor as the MCP find_skill tool: secondary hits must score ≥ half the best. */
const RELEVANCE_FLOOR = 0.5;
const repoHref = (id: string) => `/catalog/${id}`;
const skillHref = (id: string) => `/repo/${id}`;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/** A repository named in a question: exact owner/name, then exact name, then a unique partial match. */
export function resolveRepo(name: string, repos: RepoFact[]): { repo: RepoFact } | { candidates: string[] } {
  const q = norm(name);
  const byKey = repos.find((r) => norm(r.key) === q) ?? repos.find((r) => norm(r.key.split("/")[1] ?? "") === q || norm(r.title) === q);
  if (byKey) return { repo: byKey };
  const partial = repos.filter((r) => norm(r.key).includes(q) || (q.length >= 3 && q.split(" ").every((w) => norm(r.key).includes(w))));
  return partial.length === 1 ? { repo: partial[0] } : { candidates: (partial.length ? partial : repos).map((r) => r.key).slice(0, 20) };
}

function scorecardOf(entityId: string, scores: ScoreFact[], facts?: EntityFacts) {
  const mine = scores.filter((s) => s.entity_id === entityId);
  const lv = facts ? levelOf(facts, mine) : null;
  return { checks: mine.map((s) => ({ check: s.check_id, title: CHECK_TITLES[s.check_id] ?? s.check_id, verdict: s.verdict, summary: s.summary, scored_at: s.created_at })),
    passing_all: mine.length > 0 && mine.every((s) => s.verdict === "pass"), scored: mine.length > 0,
    ...(lv ? { level: LEVEL_LABEL[lv.level], next_level: lv.next ? { level: LEVEL_LABEL[lv.next], rule: LEVEL_RULE[lv.next], blocked_by: lv.blockers.map((b) => `${b.title}: ${b.reason}`) } : null } : {}) };
}
const LEVEL_NOTE = "Levels: Bronze = every applicable check has run without error; Silver = none fails; Gold = all pass. A repository no check applies to has no level.";

const searchCatalog = tool({
  spec: { type: "function", function: { name: "search_catalog",
    description: "List the workspace's repositories (the software catalog) with owner, stack, applicable skills and each scorecard check's latest verdict. Filter by free text (name, owner, stack, description) and/or a failing check id (rls, tenancy, nextjs, observability).",
    parameters: { type: "object", properties: {
      query: { type: "string", description: "Words to match against repository name, owner, stack or description. Omit to list all." },
      failing_check: { type: "string", enum: Object.keys(CHECK_TITLES), description: "Only repositories whose latest verdict on this check is fail or error." },
      below_level: { type: "string", enum: ["bronze", "silver", "gold"], description: "Only repositories (that a check applies to) not yet at this scorecard level." },
      include_archived: { type: "boolean", description: "Include archived repositories (default false)." } }, additionalProperties: false } } },
  schema: z.object({ query: z.string().max(200).optional(), failing_check: z.string().max(40).optional(), below_level: z.enum(["bronze", "silver", "gold"]).optional(), include_archived: z.boolean().optional() }),
  async run(a, d) {
    const [repos, scores] = await Promise.all([d.repos(), d.scores()]);
    const words = norm(a.query ?? "").split(" ").filter((w) => w.length > 1);
    const hay = (r: RepoFact) => norm([r.key, r.title, r.owner ?? "", r.description ?? "", ...r.stack].join(" "));
    const hits = repos.filter((r) => (a.include_archived || !r.archived) && words.every((w) => hay(r).includes(w)))
      .map((r) => ({ r, card: scorecardOf(r.id, scores, r.facts) }))
      .filter(({ card }) => !a.failing_check || card.checks.some((c) => c.check === a.failing_check && (c.verdict === "fail" || c.verdict === "error")))
      .filter(({ r }) => { if (!a.below_level || !r.facts) return true; const l = levelOf(r.facts, scores.filter((x) => x.entity_id === r.id)).level; return l !== "n/a" && !atLeast(l, a.below_level); });
    const rows = hits.slice(0, 50).map(({ r, card }) => ({ repository: r.key, link: repoHref(r.id), owner: r.owner, archived: r.archived, stack: r.stack,
      description: r.description, last_activity: r.lastActivity, applicable_skills: r.applicable.map((x) => x.skill), scorecard: card }));
    return { content: { total_in_catalog: repos.length, matched: hits.length, repositories: rows, levels: LEVEL_NOTE },
      links: hits.slice(0, 50).map(({ r }) => ({ title: r.key, href: repoHref(r.id) })),
      summary: `${hits.length} of ${repos.length} repositories${a.failing_check ? ` failing ${a.failing_check}` : ""}${a.below_level ? ` below ${a.below_level}` : ""}${a.query ? ` matching “${a.query}”` : ""}` };
  },
});

const getScorecard = tool({
  spec: { type: "function", function: { name: "get_scorecard",
    description: "One repository's scorecard: each check's latest verdict on the default branch, its summary, the library skill that scored it, and when. Use the repository name (owner/name or just name).",
    parameters: { type: "object", properties: { repository: { type: "string", description: "Repository, e.g. vg-advantage-portal or owner/vg-advantage-portal." } }, required: ["repository"], additionalProperties: false } } },
  schema: z.object({ repository: z.string().min(1).max(200) }),
  async run(a, d) {
    const [repos, scores] = await Promise.all([d.repos(), d.scores()]);
    const hit = resolveRepo(a.repository, repos);
    if ("candidates" in hit) return { content: { error: `No single repository matches “${a.repository}”.`, candidates: hit.candidates }, links: [], summary: `no repository “${a.repository}”` };
    const r = hit.repo;
    const card = scorecardOf(r.id, scores, r.facts);
    return { content: { repository: r.key, levels: LEVEL_NOTE, link: repoHref(r.id), github: r.url, owner: r.owner, ...card,
      note: card.scored ? "Verdicts are the library skills' own reports on the repository's files at the scored commit." : "This repository has not been scored yet." },
      links: [{ title: `${r.key} scorecard`, href: repoHref(r.id) }],
      summary: `${r.key}: ${card.checks.map((c) => `${c.check} ${c.verdict}`).join(", ") || "not scored"}` };
  },
});

const findSkill = tool({
  spec: { type: "function", function: { name: "find_skill",
    description: "Find the library skills that fit a task described in plain words. Returns each match with what it produces and its lifecycle stage.",
    parameters: { type: "object", properties: { task: { type: "string", description: "The work to be done, in a sentence." } }, required: ["task"], additionalProperties: false } } },
  schema: z.object({ task: z.string().min(4).max(500) }),
  async run(a, d) {
    const ranked = d.route(a.task, 5);
    const top = ranked[0]?.score ?? 0;
    const hits = ranked.filter((h, i) => (i === 0 && top > 0) || (i > 0 && h.score >= top * RELEVANCE_FLOOR)).map((h) => d.skill(h.skill)).filter((s): s is SkillFact => !!s);
    return { content: { task: a.task, matches: hits.map((s) => ({ skill: s.id, name: s.name, stage: s.stage, produces: s.card, link: skillHref(s.id) })) },
      links: hits.map((s) => ({ title: s.name, href: skillHref(s.id) })), summary: `${hits.length} skill(s) for “${a.task}”` };
  },
});

const listRuns = tool({
  spec: { type: "function", function: { name: "list_automation_runs",
    description: "Recent workflow-automation runs (pull-request gates and default-branch scorecard updates): automation, repository, PR, commit, per-check verdicts, and the GitHub check link. Newest first.",
    parameters: { type: "object", properties: {
      repository: { type: "string", description: "Only this repository (owner/name or name)." },
      pr_number: { type: "integer", description: "Only runs for this pull request number." },
      limit: { type: "integer", minimum: 1, maximum: 25, description: "How many (default 10)." } }, additionalProperties: false } } },
  schema: z.object({ repository: z.string().max(200).optional(), pr_number: z.number().int().positive().optional(), limit: z.number().int().min(1).max(25).optional() }),
  async run(a, d) {
    let runs = await d.automationRuns(100);
    if (a.repository) {
      const hit = resolveRepo(a.repository, await d.repos());
      runs = "repo" in hit ? runs.filter((r) => r.repo === hit.repo.key) : runs.filter((r) => norm(r.repo).includes(norm(a.repository!)));
    }
    if (a.pr_number) runs = runs.filter((r) => r.pr_number === a.pr_number);
    const shown = runs.slice(0, a.limit ?? 10);
    return { content: { matched: runs.length, runs: shown.map((r) => ({ when: r.started_at, automation: r.automation, repository: r.repo,
      trigger: r.event === "pull_request" ? `pull request #${r.pr_number}` : "default branch", commit: r.head_sha?.slice(0, 7) ?? null, status: r.status,
      verdicts: r.verdicts, error: r.error, github_check: r.check_run_url })), all_runs_link: "/automations" },
      links: [{ title: "Automation runs", href: "/automations" }, ...shown.filter((r) => r.check_run_url).slice(0, 5).map((r) => ({ title: `${r.repo}${r.pr_number ? ` #${r.pr_number}` : ""} check`, href: r.check_run_url! }))],
      summary: `${runs.length} automation run(s)` };
  },
});

const insightsSummary = tool({
  spec: { type: "function", function: { name: "insights_summary",
    description: "Usage and value over a period: runs, success rate, people, channels, spend, scorecard pass rates, and hours saved per skill. Hours saved come only from admin-set baselines (owner and source shown); skills without a baseline have no hours.",
    parameters: { type: "object", properties: { days: { type: "integer", enum: [7, 30, 90], description: "Period in days (default 30)." } }, additionalProperties: false } } },
  schema: z.object({ days: z.union([z.literal(7), z.literal(30), z.literal(90)]).optional() }),
  async run(a, d) {
    const days = a.days ?? 30;
    const i = await d.insights(days);
    return { content: { period_days: days, runs: i.total, succeeded: i.ok, success_rate: i.successRate, people: i.people, channels: i.channels.filter((c) => c.runs > 0),
      spend_usd: i.spend.usd, runs_with_cost: i.spend.runsWithCost, scorecards: i.scorecards,
      hours_saved: { total: i.roi.hours, counted_runs: i.roi.counted, skills_with_baseline: i.roi.skillsWithBaseline, skills_without_baseline: i.roi.skillsWithout },
      by_skill: i.skills.filter((s) => s.runs > 0).slice(0, 15).map((s) => ({ skill: s.skill, runs: s.runs, counted: s.counted, hours: s.hours,
        baseline: s.baseline ? { manual_minutes: s.baseline.manual_minutes, owner: s.baseline.owner, source: s.baseline.source } : null })),
      note: "Hours saved = counted successful runs × the baseline's manual minutes. Example and evaluation runs are not counted." },
      links: [{ title: `Insights (${days} days)`, href: `/insights?days=${days}` }], summary: `${i.total} run(s) in ${days} days, ${i.roi.hours} h saved` };
  },
});

const listInitiatives = tool({
  spec: { type: "function", function: { name: "list_initiatives",
    description: "The workspace's initiatives: a scorecard level set as a goal for some or all repositories, with owner, deadline, status, and live progress (which repositories meet the target and what blocks the rest).",
    parameters: { type: "object", properties: { include_closed: { type: "boolean", description: "Include closed initiatives (default false)." } }, additionalProperties: false } } },
  schema: z.object({ include_closed: z.boolean().optional() }),
  async run(a, d) {
    if (!d.initiatives) return { content: { error: "initiatives are not available here" }, links: [], summary: "no initiatives source" };
    const [inis, repos, scores] = await Promise.all([d.initiatives(), d.repos(), d.scores()]);
    const latest = new Map<string, ScoreFact[]>();
    for (const sc of scores) latest.set(sc.entity_id, [...(latest.get(sc.entity_id) ?? []), sc]);
    const ents = repos.filter((r) => !r.archived && r.facts).map((r) => ({ id: r.id, key: r.key, properties: { stack: r.facts!.stackIds.map((id) => ({ id })), counts: r.facts!.counts } }));
    const shown = inis.filter((i) => a.include_closed || i.status === "active");
    const rows = shown.map((i) => { const p = progressOf(i, ents, latest);
      return { title: i.title, target_level: LEVEL_LABEL[i.target_level], owner: i.owner, due_on: i.due_on, status: i.status, state: i.created_at ? initiativeState(p, { created_at: i.created_at, due_on: i.due_on, status: i.status }) : null, days_left: p.daysLeft, overdue: p.overdue,
        progress: `${p.met} of ${p.total} repositories (${p.pct}%)`,
        repositories: p.repos.map((r) => ({ repository: r.key, link: r.id ? repoHref(r.id) : null, meets_target: r.met, level: r.result ? LEVEL_LABEL[r.result.level] : null,
          blocked_by: r.met ? [] : (r.result?.blockers ?? []).map((b) => `${b.title}: ${b.reason}`), note: r.note ?? null })) }; });
    return { content: { initiatives: rows, all_initiatives_link: "/initiatives", levels: LEVEL_NOTE },
      links: [{ title: "Initiatives", href: "/initiatives" }], summary: `${rows.length} initiative(s)` };
  },
});

const deliveryMetrics = tool({
  spec: { type: "function", function: { name: "delivery_metrics",
    description: "Delivery (DORA-style) metrics per repository from GitHub: deploys per week (production deployments, else merges to the default branch), lead time (PR opened → merged, median and p75), change-failure proxy (revert/hotfix merges), open PRs, with DORA 2024 bands for frequency and lead time and notes on what was measured.",
    parameters: { type: "object", properties: {
      repository: { type: "string", description: "Only this repository (owner/name or name)." },
      days: { type: "integer", enum: [30, 90], description: "Window (default 30)." } }, additionalProperties: false } } },
  schema: z.object({ repository: z.string().max(200).optional(), days: z.union([z.literal(30), z.literal(90)]).optional() }),
  async run(a, d) {
    if (!d.delivery) return { content: { error: "delivery metrics are not available here" }, links: [], summary: "no delivery source" };
    let rows = await d.delivery();
    if (a.repository) { const hit = resolveRepo(a.repository, await d.repos()); rows = "repo" in hit ? rows.filter((r) => r.entity_id === hit.repo.id) : []; }
    const w = a.days ?? 30;
    return { content: { window_days: w, measured: rows.length, repositories: rows.map((r) => ({ repository: r.key, link: repoHref(r.entity_id), measured_at: r.computed_at, notes: r.notes, metrics: w === 90 ? r.d90 : r.d30 })),
      definitions: "deploys.source 'merges' means GitHub deployments were not readable, so merges to the default branch are counted. lead_time is PR open→merge (approximates commit→production). change_failure is a revert/hotfix proxy; no incident data. Bands: DORA 2024 clusters.", page: "/insights#delivery" },
      links: [{ title: "Delivery on Insights", href: "/insights#delivery" }], summary: `${rows.length} repositor${rows.length === 1 ? "y" : "ies"} measured` };
  },
});

const listAiAssets = tool({
  spec: { type: "function", function: { name: "list_ai_assets",
    description: "AI assets found in the catalog's repositories: agents (frameworks proved by a dependency, definition files), MCP servers, skills (SKILL.md folders), MCP client configs and agent-instruction files — each with its repository, path and evidence.",
    parameters: { type: "object", properties: {
      kind: { type: "string", enum: ["agent", "mcp_server", "skill", "mcp_config", "agent_instructions"], description: "Only this kind." },
      repository: { type: "string", description: "Only this repository (owner/name or name)." } }, additionalProperties: false } } },
  schema: z.object({ kind: z.enum(["agent", "mcp_server", "skill", "mcp_config", "agent_instructions"]).optional(), repository: z.string().max(200).optional() }),
  async run(a, d) {
    let repos = (await d.repos()).filter((r) => !r.archived);
    if (a.repository) { const hit = resolveRepo(a.repository, repos); repos = "repo" in hit ? [hit.repo] : []; }
    const all = repos.flatMap((r) => (r.aiAssets ?? []).filter((x) => !a.kind || x.kind === a.kind).map((x) => ({ ...x, repository: r.key, link: repoHref(r.id) })));
    const counts = Object.fromEntries(["agent", "mcp_server", "skill", "mcp_config", "agent_instructions"].map((k) => [k, all.filter((x) => x.kind === k).length]));
    return { content: { scanned_repositories: repos.filter((r) => Array.isArray(r.aiAssets)).length, counts, assets: all.slice(0, 80), truncated: all.length > 80, page: "/ai-assets" },
      links: [{ title: "AI assets", href: a.kind ? `/ai-assets?kind=${a.kind}` : "/ai-assets" }], summary: `${all.length} AI asset(s)` };
  },
});

const searchEntities = tool({
  spec: { type: "function", function: { name: "search_services_and_databases",
    description: "Services (Vercel projects) and databases (Supabase projects) in the catalog, with their relations: the repository a service is built from, the database it uses, the services using a database; plus production URL, last production deploy, deploys in 30 days, database status/region/version.",
    parameters: { type: "object", properties: {
      kind: { type: "string", enum: ["service", "database"], description: "Only services or only databases." },
      query: { type: "string", description: "Words to match against name, repository or URL." } }, additionalProperties: false } } },
  schema: z.object({ kind: z.enum(["service", "database"]).optional(), query: z.string().max(200).optional() }),
  async run(a, d) {
    if (!d.entities || !d.relations) return { content: { error: "services and databases are not available here" }, links: [], summary: "no entity source" };
    const [ents, rels, repos] = await Promise.all([d.entities(), d.relations(), d.repos()]);
    const name = new Map<string, string>([...ents.map((e) => [e.id, e.kind === "database" ? `${e.title} (${e.key})` : e.title] as [string, string]), ...repos.map((r) => [r.id, r.key] as [string, string])]);
    const words = norm(a.query ?? "").split(" ").filter((w) => w.length > 1);
    const hits = ents.filter((e) => (!a.kind || e.kind === a.kind) && words.every((w) => norm([e.title, e.key, e.url, String(e.properties.repo ?? ""), String(e.properties.production_url ?? "")].join(" ")).includes(w)));
    const rows = hits.slice(0, 60).map((e) => {
      const { prod_deploys: _drop, ...props } = e.properties as Record<string, unknown>; void _drop;
      return { kind: e.kind, name: e.title, key: e.key, link: `/catalog/${e.id}`, source: e.source, properties: props,
        relations: rels.filter((r) => r.from === e.id || r.to === e.id).map((r) => ({ type: r.type, direction: r.from === e.id ? "out" : "in", other: name.get(r.from === e.id ? r.to : r.from) ?? "(unknown)", other_link: `/catalog/${r.from === e.id ? r.to : r.from}`, evidence: r.evidence })) };
    });
    return { content: { total: ents.length, matched: hits.length, entities: rows, note: "built_from: service → repository (Vercel Git link). uses_database: service → database (the Supabase project its SUPABASE_URL setting names)." },
      links: hits.slice(0, 10).map((e) => ({ title: e.title, href: `/catalog/${e.id}` })), summary: `${hits.length} ${a.kind ?? "service/database"} entit${hits.length === 1 ? "y" : "ies"}` };
  },
});

const TOOLS = [searchCatalog, getScorecard, findSkill, listRuns, insightsSummary, listInitiatives, deliveryMetrics, listAiAssets, searchEntities];
export const TOOL_SPECS: ToolSpec[] = TOOLS.map((t) => t.spec);

/** Run one tool call from the model. Bad names or arguments come back as tool errors the model can correct. */
export async function runTool(name: string, rawArgs: string, d: AssistantData): Promise<ToolResult & { ok: boolean; args: unknown }> {
  const t = TOOLS.find((x) => x.spec.function.name === name);
  if (!t) return { ok: false, args: null, content: { error: `unknown tool ${name}` }, links: [], summary: `unknown tool ${name}` };
  let parsed: unknown;
  try { parsed = rawArgs ? JSON.parse(rawArgs) : {}; } catch { return { ok: false, args: rawArgs.slice(0, 200), content: { error: "arguments are not valid JSON" }, links: [], summary: "bad arguments" }; }
  const v = t.schema.safeParse(parsed);
  if (!v.success) return { ok: false, args: parsed, content: { error: "invalid arguments", issues: v.error.issues.map((i: z.ZodIssue) => `${i.path.join(".")}: ${i.message}`) }, links: [], summary: "invalid arguments" };
  try { return { ok: true, args: v.data, ...(await t.run(v.data, d)) }; }
  catch (e) { return { ok: false, args: v.data, content: { error: `could not read the data: ${(e as Error).message}` }, links: [], summary: "data read failed" }; }
}
