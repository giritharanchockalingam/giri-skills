"use server";
/* Server actions for the Deliver page. Input parsed with zod; the role and pipeline-access rules are enforced in
 * lib/delivery/server and again in the database (sf_delivery_run_start, sf_delivery_run_set_stage). */
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireWorkspace } from "@/lib/factory/db";
import { fromForm, StartDeliveryForm, ApproveDeliveryForm, DeliveryStartInput, ComposeDeliveryForm, StartComposedDeliveryForm, ComposeInputSchema } from "@/lib/validation";
import { DeliveryError, approveStage, startForSession } from "@/lib/delivery/server";
import { ComposeError, type ComposeResult } from "@/lib/delivery/compose";
import { composeWithData } from "@/lib/delivery/composeData";
import { loadCatalog } from "@/lib/db/catalog";
import type { WsCtx } from "@/lib/factory/db";
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

/** What the Deliver page shows after a composition: the pipeline's shape, the notes and the decision table (the JSON itself
 *  is re-composed on start — composition is deterministic — so nothing a browser sends is trusted as a pipeline). */
export type ComposeActionResult = ActionResult & { composed?: { name: string; stacks: string[]; stages: { id: string; role: string; steps: string[] }[]; notes: string[];
  decisions: ComposeResult["decisions"]; request_kind: string; mode: string } };

/** The composition for a catalog repository: its stack signals (synced from GitHub) decide which skills fit. */
async function composeForRepo(ctx: WsCtx, input: ComposeInputSchema): Promise<{ result: ComposeResult; stacks: string[] }> {
  const catalog = await loadCatalog(ctx.supabase, ctx.workspace.id);
  const entity = catalog.entities.find((e) => e.key === input.repo && !e.archived);
  if (!entity) throw new DeliveryError(404, "not_in_catalog", `${input.repo} is not in this workspace's catalog. Sync it under Platform → Repositories first (its stack decides which skills fit).`);
  const stacks = (entity.properties.stack ?? []).map((s) => s.id);
  return { result: composeWithData({ stacks, requestKind: input.request_kind, mode: input.mode }), stacks };
}

/** "No template fits? Compose one": composes for the repository and request kind and shows the decision table. Nothing is persisted. */
export async function composeDelivery(_: ComposeActionResult | null, fd: FormData): Promise<ComposeActionResult> {
  const form = ComposeDeliveryForm.parse(fromForm(ComposeDeliveryForm, fd));
  const parsed = ComposeInputSchema.safeParse({ repo: form.repo, request_kind: form.request_kind, mode: form.mode || undefined });
  if (!parsed.success) return fail(parsed.error.issues.map((i) => `${i.path.join(".") || "input"}: ${i.message}`).join("; "));
  try {
    const ctx = await requireWorkspace();
    const { result, stacks } = await composeForRepo(ctx, parsed.data);
    const p = result.pipeline;
    if (!p) return { ok: false, message: result.notes.join("; "), composed: { name: "", stacks, stages: [], notes: result.notes, decisions: result.decisions, request_kind: parsed.data.request_kind, mode: parsed.data.mode ?? "" } };
    return { ok: true, message: `Composed ${p.name}: ${p.stages.length} stage${p.stages.length === 1 ? "" : "s"}${result.notes.length ? ` (${result.notes.length} dropped)` : ""}.`,
      composed: { name: p.name, stacks, stages: p.stages.map((s) => ({ id: s.id, role: s.role, steps: s.steps.map((t) => String(t.skill ?? `${t.id} [${t.kind}]`)) })),
        notes: result.notes, decisions: result.decisions, request_kind: p.composed.request_kind, mode: p.mode } };
  } catch (e) {
    if (e instanceof ComposeError) return fail(e.message);
    return fail(errMsg(e));
  }
}

/** Starts a run with a composed pipeline: re-composed server-side from the same inputs, stored on the run as pipeline_spec. */
export async function startComposedDelivery(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const form = StartComposedDeliveryForm.parse(fromForm(StartComposedDeliveryForm, fd));
  const parsed = ComposeInputSchema.safeParse({ repo: form.repo, request_kind: form.request_kind, mode: form.mode || undefined });
  if (!parsed.success) return fail(parsed.error.issues.map((i) => `${i.path.join(".") || "input"}: ${i.message}`).join("; "));
  let id: string;
  try {
    const ctx = await requireWorkspace();
    const { result } = await composeForRepo(ctx, parsed.data);
    if (!result.pipeline) return fail(result.notes.join("; "));
    const start = DeliveryStartInput.safeParse({ pipeline: result.pipeline.name, repo: form.repo, ref: form.ref, request: form.request, executor: form.executor || "github-actions" });
    if (!start.success) return fail(start.error.issues.map((i) => `${i.path.join(".") || "input"}: ${i.message}`).join("; "));
    const r = await startForSession(ctx, start.data, await portalUrl(), result.pipeline);
    id = r.run.id;
  } catch (e) {
    if (e && typeof e === "object" && "digest" in e && String((e as { digest: string }).digest).startsWith("NEXT_REDIRECT")) throw e;
    if (e instanceof ComposeError) return fail(e.message);
    return fail(errMsg(e));
  }
  revalidatePath("/deliver");
  redirect(`/deliver/${id}`);
}
