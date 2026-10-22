"use server";
/* Server actions for the Deliver page. Input parsed with zod; the role and pipeline-access rules are enforced in
 * lib/delivery/server and again in the database (sf_delivery_run_start, sf_delivery_run_set_stage). */
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { fromForm, StartDeliveryForm, ApproveDeliveryForm, DeliveryStartInput } from "@/lib/validation";
import { DeliveryError, approveStage, startForSession } from "@/lib/delivery/server";
import { portalUrl } from "@/lib/delivery/config";
import type { ActionResult } from "@/app/actions";

const fail = (message: string): ActionResult => ({ ok: false, message });
const errMsg = (e: unknown) => (e instanceof DeliveryError ? e.message : e instanceof Error ? e.message : String(e)).replace(/^[a-z_]+: /, "");

/** Starts a run from the Deliver form and opens it. */
export async function startDelivery(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const form = StartDeliveryForm.parse(fromForm(StartDeliveryForm, fd));
  const parsed = DeliveryStartInput.safeParse({ pipeline: form.pipeline, repo: form.repo, ref: form.ref, request: form.request, executor: form.executor || "github-actions" });
  if (!parsed.success) return fail(parsed.error.issues.map((i) => `${i.path.join(".") || "input"}: ${i.message}`).join("; "));
  let id: string;
  try {
    const ctx = await requireWorkspace();
    const r = await startForSession(ctx, parsed.data, await portalUrl());
    id = r.run.id;
  } catch (e) {
    if (e && typeof e === "object" && "digest" in e && String((e as { digest: string }).digest).startsWith("NEXT_REDIRECT")) throw e;
    return fail(errMsg(e));
  }
  revalidatePath("/deliver");
  redirect(`/deliver/${id}`);
}

/** Approves the stage a run waits on (authority: admin, or a holder of the stage's role). */
export async function approveDelivery(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const form = ApproveDeliveryForm.parse(fromForm(ApproveDeliveryForm, fd));
  try {
    const ctx = await requireWorkspace();
    const next = await approveStage(ctx, form.run_id, form.stage_id, form.note);
    await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "delivery.approve", p_entity_type: "delivery_run", p_entity_id: form.run_id, p_details: { stage: form.stage_id, note: form.note, status: next.status } });
  } catch (e) {
    if (e && typeof e === "object" && "digest" in e && String((e as { digest: string }).digest).startsWith("NEXT_REDIRECT")) throw e;
    return fail(errMsg(e));
  }
  revalidatePath(`/deliver/${form.run_id}`);
  return { ok: true, message: `Approved “${form.stage_id}”. The executor continues from here.` };
}
