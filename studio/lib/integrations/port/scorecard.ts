/* skill_quality scorecard on the AI Skill blueprint (spec §4.2). Rules test synced sf_ properties only — Port displays
 * and enforces, it never recomputes trigger/lift. Levels Basic → Bronze → Silver → Gold. Gold thresholds are owner
 * decision D3 (2026-10-24): Silver + trigger ≥ 0.90 + lift ≥ +0.30 + ≥ 6 eval cases. */
export const GOLD = { minTrigger: 0.9, minLift: 0.3, minCases: 6 } as const;
import type { PortClient } from "./client";
import { BLUEPRINT_ID } from "./map";

export const SCORECARD_ID = "skill_quality";

export const SKILL_QUALITY_SCORECARD = {
  identifier: SCORECARD_ID,
  title: "Skill quality",
  levels: [
    { title: "Basic", color: "lightGray" },
    { title: "Bronze", color: "bronze" },
    { title: "Silver", color: "silver" },
    { title: "Gold", color: "gold" },
  ],
  rules: [
    {
      identifier: "published_with_verdict", title: "Published with an eval verdict", level: "Bronze",
      description: "The live version is published and the Skills Factory eval harness has recorded a verdict for it.",
      query: { combinator: "and", conditions: [
        { property: "sf_status", operator: "=", value: "published" },
        { property: "sf_eval_verdict", operator: "isNotEmpty" },
      ] },
    },
    {
      identifier: "healthy_and_approved", title: "Healthy verdict, approval pinned to current content", level: "Silver",
      description: "Verdict is healthy and the approval hash equals the current content hash (not stale).",
      query: { combinator: "and", conditions: [
        { property: "sf_status", operator: "=", value: "published" },
        { property: "sf_eval_verdict", operator: "=", value: "healthy" },
        { property: "sf_approval_valid", operator: "=", value: true },
      ] },
    },
    {
      identifier: "gold_quality", title: "Routes reliably and clearly improves answers", level: "Gold",
      description: "Silver, and trigger ≥ 0.90, lift ≥ +0.30 and at least 6 eval cases (owner decision D3).",
      query: { combinator: "and", conditions: [
        { property: "sf_status", operator: "=", value: "published" },
        { property: "sf_eval_verdict", operator: "=", value: "healthy" },
        { property: "sf_approval_valid", operator: "=", value: true },
        { property: "sf_trigger_score", operator: ">=", value: GOLD.minTrigger },
        { property: "sf_lift", operator: ">=", value: GOLD.minLift },
        { property: "sf_eval_cases", operator: ">=", value: GOLD.minCases },
      ] },
    },
  ],
} as const;

/** Create the scorecard, or replace it when its rules/levels differ from this definition. Returns what happened. */
export async function ensureSkillQualityScorecard(port: PortClient): Promise<"created" | "updated" | "current"> {
  const existing = (await port.listScorecards(BLUEPRINT_ID)).find((s) => s.identifier === SCORECARD_ID);
  if (!existing) { await port.createScorecard(BLUEPRINT_ID, SKILL_QUALITY_SCORECARD); return "created"; }
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  const want = SKILL_QUALITY_SCORECARD;
  const rulesMatch = same((existing.rules as unknown[] | undefined)?.map((r) => strip(r as Record<string, unknown>)), want.rules.map((r) => strip(r as unknown as Record<string, unknown>)));
  const levelsMatch = same(((existing.levels as { title: string }[] | undefined) ?? []).map((l) => l.title), want.levels.map((l) => l.title));
  if (rulesMatch && levelsMatch) return "current";
  await port.replaceScorecard(BLUEPRINT_ID, want);
  return "updated";
}
const strip = (r: Record<string, unknown>) => ({ identifier: r.identifier, level: r.level, query: r.query });

export interface ScorecardReadback { slug: string; level: string | null; rules: { identifier: string; status: string }[]; verdict: unknown; approvalValid: unknown; status: unknown }

/** Port's own computed level for each skill — the contract test's evidence (read, never derived here). */
export async function readbackLevels(port: PortClient, slugs: string[]): Promise<ScorecardReadback[]> {
  const out: ScorecardReadback[] = [];
  for (const slug of slugs) {
    const e = await port.getEntity(BLUEPRINT_ID, slug);
    const props = (e?.properties ?? {}) as Record<string, unknown>;
    const sc = ((e?.scorecards ?? {}) as Record<string, { level?: string; rules?: { identifier: string; status: string }[] }>)[SCORECARD_ID];
    out.push({ slug, level: e ? sc?.level ?? null : null, rules: sc?.rules?.map((r) => ({ identifier: r.identifier, status: r.status })) ?? [], verdict: props.sf_eval_verdict ?? null, approvalValid: props.sf_approval_valid ?? null, status: props.sf_status ?? null });
  }
  return out;
}

/** Generic create-or-replace of a scorecard on any blueprint (used for the PR review gate). */
export async function ensureScorecard(port: PortClient, blueprint: string, def: { identifier: string; levels: readonly { title: string }[]; rules: readonly unknown[] }): Promise<"created" | "updated" | "current"> {
  const existing = (await port.listScorecards(blueprint)).find((s) => s.identifier === def.identifier);
  if (!existing) { await port.createScorecard(blueprint, def); return "created"; }
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  const rulesMatch = same((existing.rules as unknown[] | undefined)?.map((r) => strip(r as Record<string, unknown>)), def.rules.map((r) => strip(r as Record<string, unknown>)));
  const levelsMatch = same(((existing.levels as { title: string }[] | undefined) ?? []).map((l) => l.title), def.levels.map((l) => l.title));
  if (rulesMatch && levelsMatch) return "current";
  await port.replaceScorecard(blueprint, def);
  return "updated";
}
