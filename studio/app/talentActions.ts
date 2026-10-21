"use server";
/* Roles and talent pools: create (blank or from a template), save drafts, publish, and route a task to a role's skills.
 * Every write is role-checked here AND by RLS/RPC in the database. Creating from a template also creates what it
 * depends on in this workspace (a pool's roles, a role's playbook agents) from their shipped templates. */
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireWorkspace, type WsCtx } from "@/lib/factory/db";
import { can, type Action } from "@/lib/factory/roles";
import { canonicalJson } from "@/lib/factory/manifest";
import { sha256 } from "@/lib/factory/hash";
import { validateRoleSpec, validatePoolSpec, type RoleSpec, type PoolSpec } from "@/lib/factory/talent";
import { ROLE_TEMPLATES, POOL_TEMPLATES, skillMap, getRouter, workspacePlaybooks, workspaceRoles } from "@/lib/factory/talentData";
import type { AgentSpec } from "@/lib/factory/agents";
import agentTemplates from "@/data/agent-templates.json";
import type { ActionResult } from "@/app/actions";
import { fromForm, CreateTalentForm, SaveTalentDraftForm, NewTalentDraftForm, PublishTalentVersionForm, RouteTaskArgs, RouteAnyTaskArgs } from "@/lib/validation";

type Kind = "role" | "pool";
const ok = (message: string, extra: Record<string, unknown> = {}): ActionResult => ({ ok: true, message, ...extra }) as ActionResult;
const fail = (message: string): ActionResult => ({ ok: false, message });
const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "x";
const hashOf = (spec: unknown) => sha256(canonicalJson(spec));
const audit = (ctx: WsCtx, action: string, type: string, id: string, details: Record<string, unknown> = {}) =>
  ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: action, p_entity_type: type, p_entity_id: id, p_details: details });

async function guarded(action: Action, fn: (ctx: WsCtx) => Promise<ActionResult>): Promise<ActionResult> {
  try {
    const ctx = await requireWorkspace();
    if (!can(ctx.role, action)) return fail(`Your role (${ctx.role}) cannot do this.`);
    return await fn(ctx);
  } catch (e) {
    if (e && typeof e === "object" && "digest" in e && String((e as { digest: string }).digest).startsWith("NEXT_REDIRECT")) throw e;
    return fail(e instanceof Error ? e.message : String(e));
  }
}

/** Create an agent from its shipped template unless the workspace already has one with that slug. */
async function ensureAgent(ctx: WsCtx, name: string): Promise<string | null> {
  const { data: have } = await ctx.supabase.from("sf_agents").select("id").eq("workspace_id", ctx.workspace.id).eq("slug", name).maybeSingle();
  if (have) return null;
  const tpl = (agentTemplates as unknown as { name: string; spec: AgentSpec }[]).find((t) => t.name === name);
  if (!tpl) return `playbook ${name} has no template`;
  const { data: a, error } = await ctx.supabase.from("sf_agents").insert({ workspace_id: ctx.workspace.id, slug: name, name, description: tpl.spec.description, owner_id: ctx.user.id }).select("id").single();
  if (error) return error.message;
  const { error: ve } = await ctx.supabase.from("sf_agent_versions").insert({ agent_id: a.id, version: 1, spec: tpl.spec, spec_hash: hashOf(tpl.spec), created_by: ctx.user.id, change_note: `from template ${name}` });
  if (ve) return ve.message;
  await audit(ctx, "agent.create", "agent", a.id, { slug: name, template: name, via: "talent" });
  return null;
}

async function insertTalent(ctx: WsCtx, kind: Kind, slug: string, title: string, spec: RoleSpec | PoolSpec, basedOn: string | null): Promise<string | null> {
  const { data: t, error } = await ctx.supabase.from("sf_talent")
    .insert({ workspace_id: ctx.workspace.id, kind, slug, name: title, description: spec.description, based_on: basedOn, owner_id: ctx.user.id }).select("id").single();
  if (error) return error.message.includes("duplicate") ? `A ${kind} called "${slug}" already exists.` : error.message;
  const { error: ve } = await ctx.supabase.from("sf_talent_versions")
    .insert({ talent_id: t.id, version: 1, spec, spec_hash: hashOf(spec), created_by: ctx.user.id, change_note: basedOn ? `from template ${basedOn}` : "blank" });
  if (ve) return ve.message;
  await audit(ctx, `${kind}.create`, kind, t.id, { slug, template: basedOn });
  return null;
}

/** Create a role from a template (its playbook agents come along) unless the workspace already has it. */
async function ensureRole(ctx: WsCtx, name: string): Promise<string | null> {
  const { data: have } = await ctx.supabase.from("sf_talent").select("id").eq("workspace_id", ctx.workspace.id).eq("kind", "role").eq("slug", name).maybeSingle();
  if (have) return null;
  const tpl = ROLE_TEMPLATES.find((r) => r.name === name);
  if (!tpl) return `role ${name} has no template`;
  for (const pb of tpl.playbooks) { const e = await ensureAgent(ctx, pb); if (e) return e; }
  return insertTalent(ctx, "role", name, tpl.title, { ...tpl, based_on: tpl.name }, tpl.name);
}

export async function createTalent(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = CreateTalentForm.parse(fromForm(CreateTalentForm, fd));
  const kind: Kind = input.kind;
  let slug = "";
  const res = await guarded("talent.edit", async (ctx) => {
    const title = input.name;
    const from = input.template;
    if (!title) return fail(`Give the ${kind} a name.`);
    slug = slugify(title);
    if (kind === "role") {
      const tpl = ROLE_TEMPLATES.find((t) => t.name === from);
      if (tpl) for (const pb of tpl.playbooks) { const e = await ensureAgent(ctx, pb); if (e) return fail(e); }
      const spec: RoleSpec = tpl ? { ...tpl, name: slug, title, based_on: tpl.name } : { name: slug, title, description: title, skills: [], playbooks: [], based_on: null };
      const e = await insertTalent(ctx, "role", slug, title, spec, tpl?.name ?? null);
      return e ? fail(e) : ok("Role created.");
    }
    const tpl = POOL_TEMPLATES.find((t) => t.name === from);
    if (tpl) {
      for (const m of tpl.members) { const e = await ensureRole(ctx, m.role); if (e) return fail(e); }
      for (const pb of tpl.playbooks) { const e = await ensureAgent(ctx, pb); if (e) return fail(e); }
    }
    const spec: PoolSpec = tpl ? { ...tpl, name: slug, title, based_on: tpl.name } : { name: slug, title, description: title, members: [], playbooks: [], based_on: null };
    const e = await insertTalent(ctx, "pool", slug, title, spec, tpl?.name ?? null);
    return e ? fail(e) : ok("Talent pool created.");
  });
  if (res.ok) redirect(`/${kind === "role" ? "roles" : "pools"}/${slug}`);
  return res;
}

async function problemsFor(ctx: WsCtx, kind: Kind, spec: RoleSpec | PoolSpec): Promise<string[]> {
  const playbooks = await workspacePlaybooks(ctx);
  if (kind === "role") return validateRoleSpec(spec as RoleSpec, skillMap(), playbooks);
  const sm = skillMap();
  return validatePoolSpec(spec as PoolSpec, await workspaceRoles(ctx), playbooks, (id) => sm.get(id)?.stage);
}

export async function saveTalentDraft(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = SaveTalentDraftForm.parse(fromForm(SaveTalentDraftForm, fd));
  return guarded("talent.edit", async (ctx) => {
    const kind: Kind = input.kind;
    const versionId = input.version_id;
    let spec: RoleSpec | PoolSpec;
    try { spec = JSON.parse(input.spec); } catch { return fail("Spec is not valid JSON."); }
    const { data, error } = await ctx.supabase.from("sf_talent_versions").update({ spec, spec_hash: hashOf(spec) }).eq("id", versionId).select("id, talent_id, version").single();
    if (error) return fail(error.message.includes("immutable") ? "This version is published and frozen. Start a new draft to change it." : error.message);
    await ctx.supabase.from("sf_talent").update({ name: spec.title, description: spec.description }).eq("id", data.talent_id);
    const problems = await problemsFor(ctx, kind, spec);
    await audit(ctx, `${kind}.update`, kind, data.talent_id, { version: data.version, spec_hash: hashOf(spec), problems: problems.length });
    revalidatePath(kind === "role" ? "/roles" : "/teams", "layout");
    return problems.length ? ok(`Saved with ${problems.length} problem(s) to fix before publishing.`) : ok("Saved. No problems.");
  });
}

export async function newTalentDraft(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = NewTalentDraftForm.parse(fromForm(NewTalentDraftForm, fd));
  return guarded("talent.edit", async (ctx) => {
    const id = input.talent_id;
    const { data: vs, error } = await ctx.supabase.from("sf_talent_versions").select("*").eq("talent_id", id).order("version", { ascending: false });
    if (error) return fail(error.message);
    if ((vs ?? []).some((v) => v.status === "draft")) return fail("A draft already exists.");
    const latest = vs![0];
    const { error: ie } = await ctx.supabase.from("sf_talent_versions").insert({ talent_id: id, version: latest.version + 1, spec: latest.spec, spec_hash: latest.spec_hash, created_by: ctx.user.id, change_note: `from v${latest.version}` });
    if (ie) return fail(ie.message);
    revalidatePath(input.kind === "role" ? "/roles" : "/teams", "layout");
    return ok(`Draft v${latest.version + 1} created.`);
  });
}

export async function publishTalentVersion(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = PublishTalentVersionForm.parse(fromForm(PublishTalentVersionForm, fd));
  return guarded("talent.publish", async (ctx) => {
    const kind: Kind = input.kind;
    const versionId = input.version_id;
    const { data: v } = await ctx.supabase.from("sf_talent_versions").select("spec").eq("id", versionId).single();
    if (!v) return fail("Version not found.");
    const problems = await problemsFor(ctx, kind, v.spec as RoleSpec | PoolSpec);
    if (problems.length) return fail(`Fix ${problems.length} problem(s) first: ${problems[0]}`);
    const { error } = await ctx.supabase.rpc("sf_publish_talent_version", { p_version: versionId });
    if (error) return fail(error.message);
    revalidatePath(kind === "role" ? "/roles" : "/teams", "layout");
    return ok("Published. This version is frozen.");
  });
}

export interface RouteResult { ok: boolean; message: string; hits?: { skill: string; name: string; stage: string | null; score: number; matched: string[] }[] }

/** Give a role a task: rank ITS skills for the task (BM25, deterministic). Read-only; any member may ask. */
export async function routeTask(roleSkills: string[], task: string): Promise<RouteResult> {
  try {
    await requireWorkspace();
    const [skills, taskText] = RouteTaskArgs.parse([roleSkills, task]);
    const t = taskText.trim().slice(0, 4000);
    if (t.length < 8) return { ok: false, message: "Describe the task in a sentence." };
    const sm = skillMap();
    const allowed = skills.filter((s) => sm.has(s));
    const hits = getRouter().route(t, allowed, 3).map((h) => ({ ...h, name: sm.get(h.skill)!.name, stage: sm.get(h.skill)!.stage }));
    return hits.length ? { ok: true, message: `Best match: ${hits[0].name}`, hits } : { ok: false, message: "None of this role's skills matches that task. Add a skill to the role, or rephrase." };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : String(e) };
  }
}

export interface AnyRouteHit { skill: string; name: string; stage: string | null; score: number; matched: string[]; youGet: string; owners: string[]; example: string | null }

/** The front door: rank every skill in the library for a task, with who owns it and whether an example can run now. */
export interface AnyRouteResult { ok: boolean; message: string; hits?: AnyRouteHit[] }

export async function routeAnyTask(task: string): Promise<AnyRouteResult> {
  try {
    await requireWorkspace();
    const [taskText] = RouteAnyTaskArgs.parse([task]);
    const t = taskText.trim().slice(0, 4000);
    if (t.length < 8) return { ok: false, message: "Describe the work in a sentence." };
    const { whatYouGet, ownersOf, exampleFor } = await import("@/lib/frontdoor");
    const sm = skillMap();
    const hits = getRouter().route(t, undefined, 3).map((h) => {
      const s = sm.get(h.skill)!;
      const card = (s as unknown as { card?: string }).card;
      return { ...h, name: s.name, stage: s.stage, youGet: card || whatYouGet(s.description), owners: ownersOf(h.skill), example: exampleFor(h.skill)?.prompt ?? null };
    });
    return hits.length ? { ok: true, message: "", hits } : { ok: false, message: "Nothing in the library matches that yet. Try different words, or browse the lifecycle below." };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : String(e) };
  }
}
