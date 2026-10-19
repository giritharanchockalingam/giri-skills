"use server";
/* Automations: create, enable/disable, delete (administrators). Input parsed with zod; RLS enforces the role too. */
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireWorkspace } from "@/lib/factory/db";
import { insertAutomation, setAutomationEnabled, deleteAutomation } from "@/lib/db/automations";
import { CHECKS } from "@/lib/scorecards/checks";

const CHECK_IDS = CHECKS.map((c) => c.id);
const CreateSchema = z.object({
  name: z.string().trim().min(1, "Name the automation.").max(120),
  trigger: z.enum(["github.pull_request", "github.push"]),
  repos: z.array(z.string().regex(/^[\w.-]+\/[\w.-]+$/)).max(200),
  checks: z.array(z.string().refine((c) => CHECK_IDS.includes(c), "unknown check")).max(CHECK_IDS.length),
  report_to_github: z.boolean(),
});
export type CreateResult = { ok: boolean; message: string } | null;

export async function createAutomation(_: CreateResult, fd: FormData): Promise<CreateResult> {
  const parsed = CreateSchema.safeParse({
    name: String(fd.get("name") ?? ""), trigger: String(fd.get("trigger") ?? ""),
    repos: fd.getAll("repos").map(String).filter(Boolean), checks: fd.getAll("checks").map(String).filter(Boolean),
    report_to_github: fd.get("report_to_github") === "on",
  });
  if (!parsed.success) return { ok: false, message: parsed.error.issues[0]?.message ?? "Invalid input." };
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") return { ok: false, message: "Administrators manage automations." };
  const { error } = await insertAutomation(ctx.supabase, { workspace_id: ctx.workspace.id, ...parsed.data, created_by: ctx.user.id });
  if (error) return { ok: false, message: error.message };
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "automation.create", p_entity_type: "automation", p_entity_id: parsed.data.name, p_details: parsed.data });
  revalidatePath("/automations");
  return { ok: true, message: `Automation “${parsed.data.name}” is on.` };
}

const IdSchema = z.object({ id: z.string().uuid(), enabled: z.enum(["true", "false"]).optional() });

export async function toggleAutomation(fd: FormData): Promise<void> {
  const { id, enabled } = IdSchema.parse({ id: fd.get("id"), enabled: fd.get("enabled") ?? undefined });
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") return;
  await setAutomationEnabled(ctx.supabase, ctx.workspace.id, id, enabled === "true");
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: enabled === "true" ? "automation.enable" : "automation.disable", p_entity_type: "automation", p_entity_id: id, p_details: {} });
  revalidatePath("/automations");
}

export async function removeAutomation(fd: FormData): Promise<void> {
  const { id } = IdSchema.parse({ id: fd.get("id") });
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") return;
  await deleteAutomation(ctx.supabase, ctx.workspace.id, id);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "automation.delete", p_entity_type: "automation", p_entity_id: id, p_details: {} });
  revalidatePath("/automations");
}
