/* Skills Factory → Port, the data side: load what Port must see for each published / retired skill (spec §4.1) and
 * push it. Two callers: the outbox worker (outbox.ts, service role, one skill at a time) and the admin "Push to Port"
 * button (every skill, then the worker drains). Idempotent: upsert + merge on the slug identifier. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { PortClient, portConfig } from "./client";
import { AI_SKILL_BLUEPRINT, BLUEPRINT_ID, REGISTRY_BLUEPRINT_ID, REGISTRY_RELATION, skillEntity, verdictForPort, type SkillForPort } from "./map";
import { skillDrift, contractKey } from "@/lib/factory/drift";
import { currentPin } from "@/lib/factory/pins";
import { libraryContract } from "@/lib/factory/libraryContract";
import { stageOfRepoSkill, scoreFor, meta } from "@/lib/data";
import { skillTitle } from "@/lib/names";
import type { Manifest } from "@/lib/factory/manifest";
import type { VersionSource } from "@/lib/factory/db";

export interface PortSyncResult { ok: boolean; message: string; blueprint?: "created" | "extended" | "current"; pushed: number; problems: string[] }

type VersionRow = { id: string; skill_id: string; version: number; status: string; source: VersionSource; manifest: Manifest; manifest_hash: string; published_at: string | null };
type StateRow = { version_id: string; latest_eval_pass_rate: number | string | null; eval_case_count: number; approval_valid: boolean | null; latest_eval_model: string | null; latest_eval_at: string | null };

/** The skill rows Port must mirror: every published skill at its live version, every retired skill at its last retired
 *  version. `slugs` narrows to some; `owners` (service-role callers) fills sf_owner. Drafts never appear (spec §4.1). */
export async function loadSkillsForPort(sb: SupabaseClient, workspaceId: string, opts: { slugs?: string[]; owners?: Map<string, string>; registryRepo?: string | null } = {}): Promise<{ rows: SkillForPort[]; error?: string }> {
  let q = sb.from("sf_skills").select("id, slug, name, purpose, status").eq("workspace_id", workspaceId).in("status", ["published", "retired"]);
  if (opts.slugs?.length) q = q.in("slug", opts.slugs);
  const { data: skills, error } = await q;
  if (error) return { rows: [], error: error.message };
  const ids = (skills ?? []).map((s) => s.id);
  if (!ids.length) return { rows: [] };
  const [{ data: versions }, { data: states }] = await Promise.all([
    sb.from("sf_skill_versions").select("id, skill_id, version, status, source, manifest, manifest_hash, published_at").in("skill_id", ids),
    sb.from("sf_version_release_state").select("version_id, latest_eval_pass_rate, eval_case_count, approval_valid, latest_eval_model, latest_eval_at").eq("workspace_id", workspaceId),
  ]);
  const stateOf = new Map(((states ?? []) as StateRow[]).map((s) => [s.version_id, s]));
  const rows: SkillForPort[] = [];
  for (const s of skills ?? []) {
    const vs = ((versions ?? []) as VersionRow[]).filter((v) => v.skill_id === s.id);
    const status = s.status as "published" | "retired";
    // published skill → its published version; retired skill → its most recent retired version
    const live = status === "published" ? vs.find((v) => v.status === "published") : vs.filter((v) => v.status === "retired").sort((a, b) => b.version - a.version)[0];
    if (!live) continue;
    const st = stateOf.get(live.id);
    const repo = live.source.kind === "repo" ? live.source.repo_skill : undefined;
    const score = repo ? scoreFor(repo) : null;                                   // behavioural eval harness (trigger / lift / verdict)
    const dbEvalCases = st?.eval_case_count ?? 0;
    rows.push({
      slug: s.slug, name: skillTitle(s.name), purpose: s.purpose ?? "", version: live.version, published_at: live.published_at, manifest_hash: live.manifest_hash,
      inputs: live.manifest.inputs.map((i) => ({ name: i.name, required: i.required })), usesModel: live.manifest.model_config.provider !== "none",
      evalPassRate: st?.latest_eval_pass_rate == null ? null : Number(st.latest_eval_pass_rate), evalCases: score?.evalCases ?? dbEvalCases, approved: !!st?.approval_valid,
      drift: skillDrift(vs.map((v) => ({ ...v, contract: contractKey(v.manifest as never) })), currentPin, libraryContract(repo)),
      stage: repo ? stageOfRepoSkill(repo) : null,
      status,
      verdict: verdictForPort(score?.verdict ?? null),
      triggerScore: score?.triggerAcc ?? null,
      lift: score?.lift ?? null,
      evalModel: score ? meta.model : st?.latest_eval_model ?? null,
      evalAt: st?.latest_eval_at ?? null,                                            // the harness publishes a date range, not an instant: never faked
      owner: opts.owners?.get(s.id) ?? null,
      registryFileId: repo && opts.registryRepo ? `${opts.registryRepo}/skills/${repo}/SKILL.md` : null,
    });
  }
  return { rows };
}

/** Make the blueprint carry the sf_ properties, plus the registry relation when the tenant has Port's `skill` blueprint. */
export async function ensureSkillBlueprint(port: PortClient): Promise<"created" | "extended" | "current"> {
  const hasRegistry = Boolean(await port.getBlueprint(REGISTRY_BLUEPRINT_ID));
  return port.ensureBlueprintSchema({ ...AI_SKILL_BLUEPRINT, relations: hasRegistry ? { ...REGISTRY_RELATION } : {} });
}

/** Push every published / retired skill now (admin button). The outbox stays the system of record for later changes. */
export async function syncSkillsToPort(sb: SupabaseClient, workspaceId: string, portalBase: string, f: typeof fetch = fetch, opts: { owners?: Map<string, string>; registryRepo?: string | null } = {}): Promise<PortSyncResult> {
  const cfg = portConfig(process.env);
  if (!cfg.ok) return { ok: false, message: `Port is not configured: set ${cfg.missing.join(" and ")} in Vercel.`, pushed: 0, problems: [] };
  const loaded = await loadSkillsForPort(sb, workspaceId, opts);
  if (loaded.error) return { ok: false, message: loaded.error, pushed: 0, problems: [] };
  if (!loaded.rows.length) return { ok: true, message: "No published skills to push.", pushed: 0, problems: [] };
  const port = new PortClient(cfg, f);
  let blueprint: "created" | "extended" | "current";
  try { blueprint = await ensureSkillBlueprint(port); } catch (e) { return { ok: false, message: (e as Error).message, pushed: 0, problems: [] }; }
  const problems: string[] = [];
  let pushed = 0;
  const now = new Date().toISOString();
  for (const r of loaded.rows) {
    try { await port.upsertEntity(BLUEPRINT_ID, skillEntity(r, portalBase, now)); pushed++; } catch (e) { problems.push((e as Error).message); }
  }
  return { ok: problems.length === 0, blueprint, pushed, problems,
    message: `${pushed} of ${loaded.rows.length} published or retired skills are in Port as “AI Skill” entities${blueprint === "created" ? " (blueprint created)" : blueprint === "extended" ? " (blueprint extended with sf_ properties)" : ""}.` };
}
