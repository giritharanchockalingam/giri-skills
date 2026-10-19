/* Load a workspace's recorded activity for Insights (RLS: members read their workspace). Server only. */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Activity, Baseline, Score } from "./compute";
import { exampleInputs, isExampleRun, type DemoValue, type AgentSpec } from "@/lib/factory/agents";
import templates from "@/data/agent-templates.json";
import skillDemos from "@/data/skill-demos.json";

const LIMIT = 5000;

export async function loadActivity(sb: SupabaseClient, ws: string, sinceIso: string): Promise<{ acts: Activity[]; baselines: Baseline[]; scores: Score[]; truncated: boolean }> {
  const [runs, agentRuns, browser, scored, latest, base] = await Promise.all([
    sb.from("sf_runs").select("version_id, source, status, created_at, cost_usd, invoked_by, api_key_id").eq("workspace_id", ws).gte("created_at", sinceIso).limit(LIMIT),
    sb.from("sf_agent_runs").select("steps, inputs, agent_version_id, invoked_by, created_at").eq("workspace_id", ws).gte("created_at", sinceIso).limit(LIMIT),
    sb.from("sf_browser_runs").select("skill, status, example, user_id, created_at").eq("workspace_id", ws).gte("created_at", sinceIso).limit(LIMIT),
    sb.from("sf_scorecard_results").select("skill, verdict, run_by, created_at").eq("workspace_id", ws).gte("created_at", sinceIso).limit(LIMIT),
    sb.from("sf_scorecard_latest").select("entity_id, check_id, verdict").eq("workspace_id", ws),
    sb.from("sf_roi_baselines").select("skill, manual_minutes, hourly_rate_usd, owner, source").eq("workspace_id", ws),
  ]);
  // skill identity for portal/API/eval runs: the library skill a version was imported from, else the workspace slug
  const vids = [...new Set((runs.data ?? []).map((r) => r.version_id))];
  const versions = vids.length ? (await sb.from("sf_skill_versions").select("id, skill_id, source").in("id", vids)).data ?? [] : [];
  const sids = [...new Set(versions.map((v) => v.skill_id))];
  const skills = sids.length ? (await sb.from("sf_skills").select("id, slug").in("id", sids)).data ?? [] : [];
  const slugOf = new Map(skills.map((s) => [s.id, s.slug]));
  const keyOf = new Map(versions.map((v) => [v.id, (v.source as { repo_skill?: string } | null)?.repo_skill ?? `workspace/${slugOf.get(v.skill_id) ?? "unknown"}`]));

  const acts: Activity[] = [];
  for (const r of runs.data ?? []) acts.push({ skill: keyOf.get(r.version_id) ?? "workspace/unknown", channel: r.source === "api" ? "api" : r.source === "eval" ? "eval" : "portal",
    ok: r.status === "succeeded", at: r.created_at, user: r.invoked_by ?? (r.api_key_id ? `key:${r.api_key_id}` : null), cost: r.cost_usd == null ? null : Number(r.cost_usd) });
  // playbook runs on the shipped sample inputs are examples (demos), decided from the inputs themselves
  const avIds = [...new Set((agentRuns.data ?? []).map((a) => a.agent_version_id))];
  const avs = avIds.length ? (await sb.from("sf_agent_versions").select("id, spec").in("id", avIds)).data ?? [] : [];
  const demoOf = new Map(avs.map((v) => [v.id, exampleInputs(v.spec as AgentSpec, templates as unknown as { demo: Record<string, DemoValue> }[], skillDemos as unknown as Record<string, Record<string, DemoValue>>)]));
  for (const a of agentRuns.data ?? []) {
    const example = isExampleRun(a.inputs as Record<string, { kind: string; content?: string; value?: string }>, demoOf.get(a.agent_version_id) ?? null);
    for (const s of (a.steps as { kind?: string; skill?: string; status?: string; cost_usd?: number | null }[]) ?? []) {
      if (s.kind === "skill" && s.skill) acts.push({ skill: s.skill, channel: example ? "examples" : "playbook", ok: s.status === "ok", at: a.created_at, user: a.invoked_by, cost: s.cost_usd ?? null });
    }
  }
  for (const b of browser.data ?? []) acts.push({ skill: b.skill, channel: b.example ? "examples" : "browser", ok: b.status === "succeeded", at: b.created_at, user: b.user_id, cost: null });
  for (const s of scored.data ?? []) acts.push({ skill: s.skill, channel: "scorecard", ok: s.verdict !== "error", at: s.created_at, user: s.run_by, cost: null });
  const truncated = [runs, agentRuns, browser, scored].some((q) => (q.data?.length ?? 0) >= LIMIT);
  return {
    acts, truncated,
    baselines: (base.data ?? []).map((b) => ({ ...b, manual_minutes: Number(b.manual_minutes), hourly_rate_usd: b.hourly_rate_usd == null ? null : Number(b.hourly_rate_usd) })),
    scores: (latest.data ?? []) as Score[],
  };
}
