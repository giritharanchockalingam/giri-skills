"use server";
/* Initiatives: create, close/reopen (authors and admins), delete (admins). Input parsed with zod; RLS enforces roles too. */
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireWorkspace } from "@/lib/factory/db";
import { insertInitiative, setInitiativeStatus, deleteInitiative } from "@/lib/db/initiatives";

const CreateSchema = z.object({
  title: z.string().trim().min(1, "Name the initiative.").max(140),
  description: z.string().trim().max(2000),
  target_level: z.enum(["bronze", "silver", "gold"]),
  repos: z.array(z.string().regex(/^[\w.-]+\/[\w.-]+$/)).max(200),
  owner: z.string().trim().min(1, "Name the owner (a person or team).").max(120),
  due_on: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Pick a deadline.").refine((d) => !Number.isNaN(Date.parse(d)), "Pick a valid date."),
});
export type InitiativeResult = { ok: boolean; message: string } | null;
const canWrite = (role: string) => role === "admin" || role === "author";

export async function createInitiative(_: InitiativeResult, fd: FormData): Promise<InitiativeResult> {
  const parsed = CreateSchema.safeParse({
    title: String(fd.get("title") ?? ""), description: String(fd.get("description") ?? ""), target_level: String(fd.get("target_level") ?? ""),
    repos: fd.getAll("repos").map(String).filter(Boolean), owner: String(fd.get("owner") ?? ""), due_on: String(fd.get("due_on") ?? ""),
  });
  if (!parsed.success) return { ok: false, message: parsed.error.issues[0]?.message ?? "Invalid input." };
  const ctx = await requireWorkspace();
  if (!canWrite(ctx.role)) return { ok: false, message: "Authors and administrators set initiatives." };
  const { error } = await insertInitiative(ctx.supabase, { workspace_id: ctx.workspace.id, ...parsed.data, created_by: ctx.user.id });
  if (error) return { ok: false, message: error.message };
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "initiative.create", p_entity_type: "initiative", p_entity_id: parsed.data.title, p_details: parsed.data });
  revalidatePath("/initiatives");
  return { ok: true, message: `Initiative “${parsed.data.title}” is on.` };
}

const IdSchema = z.object({ id: z.string().uuid(), status: z.enum(["active", "closed"]).optional() });

export async function changeInitiativeStatus(fd: FormData): Promise<void> {
  const { id, status } = IdSchema.parse({ id: fd.get("id"), status: fd.get("status") ?? undefined });
  const ctx = await requireWorkspace();
  if (!canWrite(ctx.role) || !status) return;
  await setInitiativeStatus(ctx.supabase, ctx.workspace.id, id, status);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: `initiative.${status === "closed" ? "close" : "reopen"}`, p_entity_type: "initiative", p_entity_id: id, p_details: {} });
  revalidatePath("/initiatives");
}

export async function removeInitiative(fd: FormData): Promise<void> {
  const { id } = IdSchema.parse({ id: fd.get("id") });
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") return;
  await deleteInitiative(ctx.supabase, ctx.workspace.id, id);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "initiative.delete", p_entity_type: "initiative", p_entity_id: id, p_details: {} });
  revalidatePath("/initiatives");
}
