/* Push every published skill of the workspace to Port as an "AI Skill" entity (creating the blueprint the first time).
 * Reads with the signed-in admin's session; writes to Port with PORT_CLIENT_ID/SECRET. Idempotent (upsert + merge). */
import type { SupabaseClient } from "@supabase/supabase-js";
import { PortClient, portConfig } from "./client";
import { AI_SKILL_BLUEPRINT, BLUEPRINT_ID, skillEntity, type SkillForPort } from "./map";
import { skillDrift, contractKey } from "@/lib/factory/drift";
import { currentPin } from "@/lib/factory/pins";
import { libraryContract } from "@/lib/factory/libraryContract";
import { stageOfRepoSkill } from "@/lib/data";
import { skillTitle } from "@/lib/names";
import type { Manifest } from "@/lib/factory/manifest";
import type { VersionSource } from "@/lib/factory/db";

export interface PortSyncResult { ok: boolean; message: string; blueprint?: "created" | "exists"; pushed: number; problems: string[] }

export async function syncSkillsToPort(sb: SupabaseClient, workspaceId: string, portalBase: string, f: typeof fetch = fetch): Promise<PortSyncResult> {
  const cfg = portConfig(process.env);
  if (!cfg.ok) return { ok: false, message: `Port is not configured: set ${cfg.missing.join(" and ")} in Vercel.`, pushed: 0, problems: [] };
  const { data: skills, error } = await sb.from("sf_skills").select("id, slug, name, purpose").eq("workspace_id", workspaceId).eq("status", "published");
  if (error) return { ok: false, message: error.message, pushed: 0, problems: [] };
  const ids = (skills ?? []).map((s) => s.id);
  if (!ids.length) return { ok: true, message: "No published skills to push.", pushed: 0, problems: [] };
  const [{ data: versions }, { data: states }] = await Promise.all([
    sb.from("sf_skill_versions").select("id, skill_id, version, status, source, manifest, manifest_hash, published_at").in("skill_id", ids),
    sb.from("sf_version_release_state").select("version_id, latest_eval_pass_rate, eval_case_count, approval_valid").eq("workspace_id", workspaceId),
  ]);
  const stateOf = new Map((states ?? []).map((s) => [s.version_id, s]));
  const rows: SkillForPort[] = [];
  for (const s of skills ?? []) {
    const vs = (versions ?? []).filter((v) => v.skill_id === s.id) as { id: string; version: number; status: string; source: VersionSource; manifest: Manifest; manifest_hash: string; published_at: string | null }[];
    const live = vs.find((v) => v.status === "published");
    if (!live) continue;
    const st = stateOf.get(live.id);
    const repo = live.source.kind === "repo" ? live.source.repo_skill : undefined;
    rows.push({
      slug: s.slug, name: skillTitle(s.name), purpose: s.purpose ?? "", version: live.version, published_at: live.published_at, manifest_hash: live.manifest_hash,
      inputs: live.manifest.inputs.map((i) => ({ name: i.name, required: i.required })), usesModel: live.manifest.model_config.provider !== "none",
      evalPassRate: st?.latest_eval_pass_rate == null ? null : Number(st.latest_eval_pass_rate), evalCases: st?.eval_case_count ?? 0, approved: !!st?.approval_valid,
      drift: skillDrift(vs.map((v) => ({ ...v, contract: contractKey(v.manifest as never) })), currentPin, libraryContract(repo)),
      stage: repo ? stageOfRepoSkill(repo) : null,
    });
  }
  const port = new PortClient(cfg, f);
  let blueprint: "created" | "exists";
  try { blueprint = await port.ensureBlueprint(AI_SKILL_BLUEPRINT); } catch (e) { return { ok: false, message: (e as Error).message, pushed: 0, problems: [] }; }
  const problems: string[] = [];
  let pushed = 0;
  for (const r of rows) {
    try { await port.upsertEntity(BLUEPRINT_ID, skillEntity(r, portalBase)); pushed++; } catch (e) { problems.push((e as Error).message); }
  }
  return { ok: problems.length === 0, blueprint, pushed, problems,
    message: `${pushed} of ${rows.length} published skills are in Port as “AI Skill” entities${blueprint === "created" ? " (blueprint created)" : ""}.` };
}
