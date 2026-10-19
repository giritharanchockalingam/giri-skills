/* Data access for the assistant: the AssistantData port backed by the signed-in user's client (RLS scopes every
 * read to their workspace), plus the question log and its rate limit. Server only. */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { AssistantData, InitiativeFact, RepoFact, RunFact, ScoreFact, SkillFact } from "@/lib/assistant/tools";
import { factsOf } from "@/lib/scorecards/levels";
import { listInitiatives } from "@/lib/db/initiatives";
import { loadDelivery } from "@/lib/db/delivery";
import type { CatalogEntityRow } from "@/lib/db/catalog";
import { computeInsights } from "@/lib/insights/compute";
import { loadActivity } from "@/lib/insights/load";
import { getRouter } from "@/lib/factory/talentData";
import { skills as repoSkills } from "@/lib/data";

type Lib = { id: string; name?: string; card?: string; stage?: string | string[] | null };
const LIB = new Map((repoSkills as unknown as Lib[]).map((s) => [s.id, s]));
const DAY = 86_400_000;

function throwIf(e: { message: string } | null) { if (e) throw new Error(e.message); }

export function assistantData(sb: SupabaseClient, ws: string): AssistantData {
  let repos: Promise<RepoFact[]> | null = null, scores: Promise<ScoreFact[]> | null = null;
  return {
    repos: () => (repos ??= (async () => {
      const { data, error } = await sb.from("sf_catalog_entities").select("id, key, title, url, owner, archived, last_activity_at, properties")
        .eq("workspace_id", ws).eq("kind", "repository").order("key");
      throwIf(error);
      return ((data ?? []) as CatalogEntityRow[]).map((e) => ({ id: e.id, key: e.key, title: e.title, url: e.url, owner: e.owner, archived: e.archived,
        description: e.properties?.description ?? null, stack: (e.properties?.stack ?? []).map((s) => s.label), lastActivity: e.last_activity_at,
        applicable: (e.properties?.applicable ?? []).map((a) => ({ skill: a.skill, why: a.why })), facts: factsOf(e.properties ?? {}) }));
    })()),
    scores: () => (scores ??= (async () => {
      const { data, error } = await sb.from("sf_scorecard_latest").select("entity_id, check_id, verdict, summary, created_at").eq("workspace_id", ws);
      throwIf(error);
      return (data ?? []) as ScoreFact[];
    })()),
    async automationRuns(limit) {
      const [r, a] = await Promise.all([
        sb.from("sf_automation_runs").select("automation_id, repo, entity_id, event, pr_number, head_sha, status, verdicts, check_run_url, error, started_at")
          .eq("workspace_id", ws).order("started_at", { ascending: false }).limit(limit),
        sb.from("sf_automations").select("id, name").eq("workspace_id", ws),
      ]);
      throwIf(r.error); throwIf(a.error);
      const name = new Map((a.data ?? []).map((x) => [x.id as string, x.name as string]));
      return (r.data ?? []).map(({ automation_id, ...x }) => ({ ...x, automation: name.get(automation_id as string) ?? "(deleted automation)" })) as RunFact[];
    },
    async insights(days) {
      const now = Date.now();
      const { acts, baselines, scores: sc } = await loadActivity(sb, ws, new Date(now - days * DAY).toISOString());
      return computeInsights(acts, baselines, sc, days, now);
    },
    initiatives: async (): Promise<InitiativeFact[]> => listInitiatives(sb, ws),
    delivery: () => loadDelivery(sb, ws),
    route: (task, k) => getRouter().route(task, undefined, k).map((h) => ({ skill: h.skill, score: h.score })),
    skill(id): SkillFact | null {
      const s = LIB.get(id);
      return s ? { id, name: s.name ?? id, stage: Array.isArray(s.stage) ? s.stage[0] ?? null : s.stage ?? null, card: s.card ?? "" } : null;
    },
  };
}

export interface AssistantLogRow { workspace_id: string; user_id: string; question: string; answer_chars: number; tools: unknown[]; model: string | null;
  prompt_tokens: number; completion_tokens: number; cost_usd: number | null; status: "answered" | "failed" | "limited"; error: string | null; duration_ms: number | null }

export async function logQuestion(sb: SupabaseClient, row: AssistantLogRow): Promise<string | null> {
  const { error } = await sb.from("sf_assistant_log").insert(row);
  return error?.message ?? null;
}

/** Questions this user asked in the last hour (their own rows are readable to them under RLS). */
export async function questionsLastHour(sb: SupabaseClient, ws: string, userId: string): Promise<number> {
  const { count, error } = await sb.from("sf_assistant_log").select("id", { count: "exact", head: true })
    .eq("workspace_id", ws).eq("user_id", userId).neq("status", "limited").gte("created_at", new Date(Date.now() - 3_600_000).toISOString());
  throwIf(error);
  return count ?? 0;
}
