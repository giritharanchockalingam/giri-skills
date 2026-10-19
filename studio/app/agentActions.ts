"use server";
/* Agent Builder mutations. Every write is role-checked here AND by RLS/RPC in the database. */
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireWorkspace, type WsCtx } from "@/lib/factory/db";
import { can, type Action } from "@/lib/factory/roles";
import { canonicalJson } from "@/lib/factory/manifest";
import { sha256 } from "@/lib/factory/hash";
import { validateAgentSpec, type AgentSpec } from "@/lib/factory/agents";
import { agentCatalog, type AgentVersionRow } from "@/lib/factory/agentRun";
import templates from "@/data/agent-templates.json";
import type { ActionResult } from "@/app/actions";

const ok = (message: string, extra: Record<string, unknown> = {}): ActionResult => ({ ok: true, message, ...extra }) as ActionResult;
const fail = (message: string): ActionResult => ({ ok: false, message });
const str = (fd: FormData, k: string, max = 10000) => String(fd.get(k) ?? "").slice(0, max).trim();
const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "agent";
const specHash = (spec: AgentSpec) => sha256(canonicalJson(spec));
const audit = (ctx: WsCtx, action: string, id: string, details: Record<string, unknown> = {}) =>
  ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: action, p_entity_type: "agent", p_entity_id: id, p_details: details });

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

/** Create an agent: blank, or from a shipped template (agents/<name>/agent.json). */
export async function createAgent(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  let slug = "";
  const res = await guarded("agent.edit", async (ctx) => {
    const name = str(fd, "name", 160);
    const from = str(fd, "template", 80);
    if (!name) return fail("Give the agent a name.");
    const tpl = (templates as { name: string; spec: AgentSpec }[]).find((t) => t.name === from);
    const spec: AgentSpec = tpl ? { ...tpl.spec, name: slugify(name) } : { name: slugify(name), description: str(fd, "description", 500) || name, inputs: [], config: { provider: "auto", on_fail: "stop" }, steps: [], outputs: [] };
    slug = slugify(name);
    const { data: agent, error } = await ctx.supabase.from("sf_agents")
      .insert({ workspace_id: ctx.workspace.id, slug, name, description: spec.description, owner_id: ctx.user.id }).select("id").single();
    if (error) return fail(error.message.includes("duplicate") ? `An agent called "${slug}" already exists.` : error.message);
    const { error: ve } = await ctx.supabase.from("sf_agent_versions")
      .insert({ agent_id: agent.id, version: 1, spec, spec_hash: specHash(spec), created_by: ctx.user.id, change_note: tpl ? `from template ${tpl.name}` : "blank" });
    if (ve) return fail(ve.message);
    await audit(ctx, "agent.create", agent.id, { slug, template: tpl?.name ?? null });
    return ok("Agent created.");
  });
  if (res.ok) redirect(`/agents/${slug}`);
  return res;
}

/** Save the Builder's spec into the draft version (published versions are frozen by the database). */
export async function saveAgentDraft(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("agent.edit", async (ctx) => {
    const versionId = str(fd, "version_id", 64);
    let spec: AgentSpec;
    try { spec = JSON.parse(String(fd.get("spec") ?? "")) as AgentSpec; } catch { return fail("Spec is not valid JSON."); }
    const problems = validateAgentSpec(spec, agentCatalog());
    const { data, error } = await ctx.supabase.from("sf_agent_versions").update({ spec, spec_hash: specHash(spec) }).eq("id", versionId).select("id, agent_id, version").single();
    if (error) return fail(error.message.includes("immutable") ? "This version is published and frozen. Start a new draft to change it." : error.message);
    await ctx.supabase.from("sf_agents").update({ description: spec.description }).eq("id", data.agent_id);
    await audit(ctx, "agent.update", data.agent_id, { version: data.version, spec_hash: specHash(spec), problems: problems.length });
    revalidatePath("/agents", "layout");
    return problems.length ? ok(`Saved with ${problems.length} problem(s) to fix before it can run.`) : ok("Saved. The agent is runnable.");
  });
}

/** Start a new draft from the latest version. */
export async function newAgentDraft(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("agent.edit", async (ctx) => {
    const agentId = str(fd, "agent_id", 64);
    const { data: vs, error } = await ctx.supabase.from("sf_agent_versions").select("*").eq("agent_id", agentId).order("version", { ascending: false });
    if (error) return fail(error.message);
    const rows = (vs ?? []) as AgentVersionRow[];
    if (rows.some((v) => v.status === "draft")) return fail("A draft already exists.");
    const latest = rows[0];
    const { error: ie } = await ctx.supabase.from("sf_agent_versions")
      .insert({ agent_id: agentId, version: (latest?.version ?? 0) + 1, spec: latest.spec, spec_hash: latest.spec_hash, created_by: ctx.user.id, change_note: `from v${latest.version}` });
    if (ie) return fail(ie.message);
    revalidatePath("/agents", "layout");
    return ok(`Draft v${(latest?.version ?? 0) + 1} created.`);
  });
}

/** Publish a draft (reviewers/admins; the RPC re-checks the role). Only a runnable spec may be published. */
export async function publishAgentVersion(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("agent.publish", async (ctx) => {
    const versionId = str(fd, "version_id", 64);
    const { data: v } = await ctx.supabase.from("sf_agent_versions").select("spec").eq("id", versionId).single();
    const problems = v ? validateAgentSpec(v.spec as AgentSpec, agentCatalog()) : ["version not found"];
    if (problems.length) return fail(`Fix ${problems.length} problem(s) first: ${problems[0]}`);
    const { error } = await ctx.supabase.rpc("sf_publish_agent_version", { p_version: versionId });
    if (error) return fail(error.message);
    revalidatePath("/agents", "layout");
    return ok("Published. This version is now frozen and runnable by every member.");
  });
}
