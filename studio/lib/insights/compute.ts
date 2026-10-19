/* Insights: adoption, quality, spend and ROI from recorded activity. Pure (no I/O) and deterministic.
 *
 * ROI rule (stated on the page): a run counts as work done when it succeeded, was not an example run on sample
 * inputs, and was not an evaluation. Hours saved = counted runs × the workspace's own baseline minutes for that
 * skill. No baseline → no hours (the skill is listed as "baseline not set"). Value = hours × the baseline's rate,
 * only when a rate was given. Spend = recorded LLM cost (provider estimates where marked). */

export type Channel = "browser" | "examples" | "portal" | "api" | "playbook" | "scorecard" | "eval";
export const CHANNEL_LABEL: Record<Channel, string> = {
  browser: "Run in the browser", examples: "Examples (sample inputs)", portal: "Run in the portal", api: "API and MCP",
  playbook: "Playbook steps", scorecard: "Scorecard checks", eval: "Evaluations",
};

export interface Activity { skill: string; channel: Channel; ok: boolean; at: string; user: string | null; cost: number | null }
export interface Baseline { skill: string; manual_minutes: number; hourly_rate_usd: number | null; owner: string; source: string }
export interface Score { entity_id: string; check_id: string; verdict: string }

export interface SkillRoi { skill: string; runs: number; counted: number; baseline: Baseline | null; hours: number | null; exactHours: number | null; value: number | null }
export interface Insights {
  periodDays: number; total: number; ok: number; successRate: number | null; people: number;
  channels: { channel: Channel; runs: number }[];
  weeks: { start: string; runs: number }[];
  skills: SkillRoi[];
  roi: { hours: number; value: number | null; counted: number; skillsWithBaseline: number; skillsWithout: number };
  spend: { usd: number; runsWithCost: number };
  scorecards: { repos: number; passingAll: number; byCheck: { check: string; pass: number; warn: number; fail: number; error: number }[] };
}

const DAY = 86_400_000;
/** Monday 00:00 UTC of the week containing t. */
export const weekStart = (t: number) => { const d = new Date(t); const dow = (d.getUTCDay() + 6) % 7; return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - dow); };
const round1 = (n: number) => Math.round(n * 10) / 10;

export function computeInsights(acts: Activity[], baselines: Baseline[], scores: Score[], periodDays: number, now = Date.now()): Insights {
  const from = now - periodDays * DAY;
  const inPeriod = acts.filter((a) => { const t = Date.parse(a.at); return t >= from && t <= now; });
  const ok = inPeriod.filter((a) => a.ok).length;
  const channels = (Object.keys(CHANNEL_LABEL) as Channel[]).map((c) => ({ channel: c, runs: inPeriod.filter((a) => a.channel === c).length }));

  const weeks: { start: string; runs: number }[] = [];
  for (let w = weekStart(from); w <= now; w += 7 * DAY) {
    weeks.push({ start: new Date(w).toISOString().slice(0, 10), runs: inPeriod.filter((a) => { const t = Date.parse(a.at); return t >= w && t < w + 7 * DAY; }).length });
  }

  const base = new Map(baselines.map((b) => [b.skill, b]));
  const counts = (a: Activity) => a.ok && a.channel !== "examples" && a.channel !== "eval";
  const bySkill = new Map<string, { runs: number; counted: number }>();
  for (const a of inPeriod) {
    const s = bySkill.get(a.skill) ?? { runs: 0, counted: 0 };
    s.runs++; if (counts(a)) s.counted++;
    bySkill.set(a.skill, s);
  }
  for (const b of baselines) if (!bySkill.has(b.skill)) bySkill.set(b.skill, { runs: 0, counted: 0 });
  const skills: SkillRoi[] = [...bySkill.entries()].map(([skill, s]) => {
    const b = base.get(skill) ?? null;
    const exact = b ? (s.counted * b.manual_minutes) / 60 : null;          // value from exact hours, display rounded
    return { skill, runs: s.runs, counted: s.counted, baseline: b, hours: exact == null ? null : round1(exact), exactHours: exact,
      value: b && b.hourly_rate_usd != null && exact != null ? Math.round(exact * b.hourly_rate_usd) : null };
  }).sort((a, b) => (b.hours ?? -1) - (a.hours ?? -1) || b.counted - a.counted || a.skill.localeCompare(b.skill));

  const withB = skills.filter((s) => s.baseline);
  const values = withB.map((s) => s.value).filter((v): v is number => v != null);
  const costs = inPeriod.map((a) => a.cost).filter((c): c is number => c != null && c > 0);

  const byEntity = new Map<string, Score[]>();
  for (const s of scores) byEntity.set(s.entity_id, [...(byEntity.get(s.entity_id) ?? []), s]);
  const checks = [...new Set(scores.map((s) => s.check_id))].sort();

  return {
    periodDays, total: inPeriod.length, ok, successRate: inPeriod.length ? ok / inPeriod.length : null,
    people: new Set(inPeriod.map((a) => a.user).filter(Boolean)).size,
    channels, weeks, skills,
    roi: { hours: round1(withB.reduce((n, s) => n + (s.exactHours ?? 0), 0)), value: values.length ? values.reduce((a, b) => a + b, 0) : null,
      counted: skills.reduce((n, s) => n + s.counted, 0), skillsWithBaseline: withB.length, skillsWithout: skills.filter((s) => !s.baseline && s.counted > 0).length },
    spend: { usd: Math.round(costs.reduce((a, b) => a + b, 0) * 100) / 100, runsWithCost: costs.length },
    scorecards: {
      repos: byEntity.size,
      passingAll: [...byEntity.values()].filter((l) => l.every((s) => s.verdict === "pass" || s.verdict === "skipped")).length,
      byCheck: checks.map((c) => {
        const l = scores.filter((s) => s.check_id === c);
        return { check: c, pass: l.filter((s) => s.verdict === "pass").length, warn: l.filter((s) => s.verdict === "warn").length, fail: l.filter((s) => s.verdict === "fail").length, error: l.filter((s) => s.verdict === "error").length };
      }),
    },
  };
}
