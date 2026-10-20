"use server";
/* Access by job role: the workspace switch and who holds which job role. Admin only, checked here AND by RLS
 * (sf_role_assignments) in the database; every change is audited. The run rule itself lives in the database. */
import { revalidatePath } from "next/cache";
import { requireWorkspace, type WsCtx } from "@/lib/factory/db";
import { can, type Action } from "@/lib/factory/roles";
import { parseHolder } from "@/lib/access";
import type { ActionResult } from "@/app/actions";
import { fromForm, SetSkillsByRoleForm, AssignRoleForm, UnassignRoleForm } from "@/lib/validation";

const ok = (message: string): ActionResult => ({ ok: true, message });
const fail = (message: string): ActionResult => ({ ok: false, message });
const audit = (ctx: WsCtx, action: string, type: string, id: string, details: Record<string, unknown> = {}) =>
  ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: action, p_entity_type: type, p_entity_id: id, p_details: details });

async function guarded(action: Action, fn: (ctx: WsCtx) => Promise<ActionResult>): Promise<ActionResult> {
  try {
    const ctx = await requireWorkspace();
    if (!can(ctx.role, action)) return fail(`Your access level (${ctx.role}) cannot do this.`);
    return await fn(ctx);
  } catch (e) {
    return fail(e instanceof Error ? e.message : String(e));
  }
}

export async function setSkillsByRole(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const { enabled } = SetSkillsByRoleForm.parse(fromForm(SetSkillsByRoleForm, fd));
  return guarded("admin.policies", async (ctx) => {
    const on = enabled === "on";
    const { data: existing } = await ctx.supabase.from("sf_policies").select("workspace_id").eq("workspace_id", ctx.workspace.id).maybeSingle();
    const { error } = existing
      ? await ctx.supabase.from("sf_policies").update({ skills_by_role: on }).eq("workspace_id", ctx.workspace.id)
      : await ctx.supabase.from("sf_policies").insert({ workspace_id: ctx.workspace.id, skills_by_role: on });
    if (error) return fail(error.message);
    await audit(ctx, "access.policy", "workspace", ctx.workspace.id, { skills_by_role: on });
    revalidatePath("/admin");
    return ok(on ? "On: people with run-only access and API keys now run only the skills in their job roles." : "Off: every member and key can run every published skill.");
  });
}

export async function assignRole(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = AssignRoleForm.parse(fromForm(AssignRoleForm, fd));
  return guarded("admin.members", async (ctx) => {
    const h = parseHolder(input.holder);
    if (!h) return fail("Choose a member or an API key.");
    const row = { workspace_id: ctx.workspace.id, talent_id: input.talent_id, granted_by: ctx.user.id, ...(h.kind === "user" ? { user_id: h.id } : { api_key_id: h.id }) };
    const { data, error } = await ctx.supabase.from("sf_role_assignments").insert(row).select("id").single();
    if (error) return fail(error.code === "23505" ? "They already hold that job role." : error.message);
    await audit(ctx, "access.assign", "role_assignment", data.id, { talent_id: input.talent_id, [h.kind === "user" ? "user_id" : "api_key_id"]: h.id });
    revalidatePath("/admin");
    return ok("Job role assigned.");
  });
}

export async function unassignRole(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const { id } = UnassignRoleForm.parse(fromForm(UnassignRoleForm, fd));
  return guarded("admin.members", async (ctx) => {
    const { data, error } = await ctx.supabase.from("sf_role_assignments").delete().eq("id", id).eq("workspace_id", ctx.workspace.id).select("talent_id, user_id, api_key_id");
    if (error) return fail(error.message);
    if (!data?.length) return fail("That assignment no longer exists.");
    await audit(ctx, "access.unassign", "role_assignment", id, data[0]);
    revalidatePath("/admin");
    return ok("Job role removed.");
  });
}
