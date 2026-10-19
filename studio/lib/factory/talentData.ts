/* Server-side loading for roles and pools: the skill catalog, the router, and the workspace's playbooks (agents).
 * Server only. */
import { skills as repoSkillsData } from "@/lib/data";
import roleTemplatesData from "@/data/role-templates.json";
import poolTemplatesData from "@/data/pool-templates.json";
import { Router, type SkillInfo, type PlaybookInfo, type RoleSpec, type PoolSpec } from "./talent";
import { isSkill, type AgentSpec } from "./agents";
import type { WsCtx } from "./db";

export const ROLE_TEMPLATES = roleTemplatesData as unknown as RoleSpec[];
export const POOL_TEMPLATES = poolTemplatesData as unknown as PoolSpec[];

type RepoRow = { id: string; name: string; stage?: string | null; description: string; bodyMd?: string; agent?: unknown };
const REPO = (repoSkillsData as unknown as RepoRow[]).filter((s) => s.agent);

/** Every executable skill (with its routing text source). */
export const SKILL_INFO: SkillInfo[] = REPO.map((s) => ({ id: s.id, name: s.name, stage: s.stage ?? null, description: s.description, bodyMd: s.bodyMd }));
export const skillMap = () => new Map(SKILL_INFO.map((s) => [s.id, s]));
/** What the client needs (no bodies). */
export const skillCatalogLite = () => SKILL_INFO.map(({ id, name, stage, description }) => ({ id, name, stage, description }));

let router: Router | null = null;
export const getRouter = () => (router ??= new Router(SKILL_INFO));

export interface TalentRow { id: string; workspace_id: string; kind: "role" | "pool"; slug: string; name: string; description: string; based_on: string | null; owner_id: string; status: string; created_at: string; updated_at: string }
export interface TalentVersionRow<S> { id: string; talent_id: string; version: number; status: "draft" | "published" | "superseded"; spec: S; spec_hash: string; change_note: string; created_at: string; published_at: string | null }

/** Workspace agents as playbooks: the published version's skills (else the latest draft's). */
export async function workspacePlaybooks(ctx: WsCtx): Promise<Map<string, PlaybookInfo & { status: string; version: number; steps: number }>> {
  const [aq, vq] = await Promise.all([
    ctx.supabase.from("sf_agents").select("id, slug").eq("workspace_id", ctx.workspace.id),
    ctx.supabase.from("sf_agent_versions").select("agent_id, version, status, spec").order("version", { ascending: false }),
  ]);
  const out = new Map<string, PlaybookInfo & { status: string; version: number; steps: number }>();
  for (const a of aq.data ?? []) {
    const vs = (vq.data ?? []).filter((v) => v.agent_id === a.id);
    const v = vs.find((x) => x.status === "published") ?? vs[0];
    if (!v) continue;
    const spec = v.spec as AgentSpec;
    out.set(a.slug, { name: a.slug, skills: (spec.steps ?? []).filter(isSkill).map((s) => s.skill), status: v.status, version: v.version, steps: spec.steps?.length ?? 0 });
  }
  return out;
}

/** The workspace's roles with the spec that counts (published, else latest draft). */
export async function workspaceRoles(ctx: WsCtx): Promise<Map<string, RoleSpec & { status: string; version: number }>> {
  const { data: ts } = await ctx.supabase.from("sf_talent").select("id, slug").eq("workspace_id", ctx.workspace.id).eq("kind", "role");
  const ids = (ts ?? []).map((t) => t.id);
  const { data: vs } = ids.length ? await ctx.supabase.from("sf_talent_versions").select("talent_id, version, status, spec").in("talent_id", ids).order("version", { ascending: false }) : { data: [] };
  const out = new Map<string, RoleSpec & { status: string; version: number }>();
  for (const t of ts ?? []) {
    const mine = (vs ?? []).filter((v) => v.talent_id === t.id);
    const v = mine.find((x) => x.status === "published") ?? mine[0];
    if (v) out.set(t.slug, { ...(v.spec as RoleSpec), name: t.slug, status: v.status, version: v.version });
  }
  return out;
}
