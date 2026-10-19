"use server";
/* Insights write paths: record a browser run (metadata only), set/remove an ROI baseline (admins). */
import { revalidatePath } from "next/cache";
import { getContext, requireWorkspace } from "@/lib/factory/db";
import { fromForm, BrowserRunInput, SaveBaselineForm, RemoveBaselineForm, SKILL_ID as SKILL } from "@/lib/validation";

export interface BrowserRun { skill: string; status: string; example: boolean; mode: string | null; checksPassed: number | null; checksTotal: number | null; durationMs: number | null }
export interface BaselineResult { ok: boolean; message: string }

/** A skill ran in this browser. Never receives inputs or outputs — only what the dashboard counts. Best effort. */
export async function recordBrowserRun(run: BrowserRun): Promise<void> {
  try {
    // an unknown skill or status is not recorded; out-of-range counts are stored as null (see BrowserRunInput)
    const parsed = BrowserRunInput.safeParse(run);
    if (!parsed.success) return;
    const r = parsed.data;
    const ctx = await getContext();
    if (!ctx.workspace) return;
    await ctx.supabase.from("sf_browser_runs").insert({
      workspace_id: ctx.workspace.id, user_id: ctx.user.id, skill: r.skill, status: r.status, example: r.example,
      mode: r.mode,
      checks_passed: r.checksPassed, checks_total: r.checksTotal, duration_ms: r.durationMs,
    });
  } catch { /* recording must never break a run */ }
}

export async function saveBaseline(_: unknown, fd: FormData): Promise<BaselineResult> {
  const input = SaveBaselineForm.parse(fromForm(SaveBaselineForm, fd));
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") return { ok: false, message: "Administrators set ROI baselines." };
  const skill = input.skill;
  const minutes = input.manual_minutes;
  const rateRaw = input.hourly_rate_usd;
  const rate = rateRaw === "" ? null : Number(rateRaw);
  const owner = input.owner;
  const source = input.source;
  if (!SKILL.test(skill)) return { ok: false, message: "Choose a skill." };
  if (!(minutes > 0 && minutes <= 10_000)) return { ok: false, message: "Manual minutes must be between 1 and 10,000." };
  if (rate !== null && !(rate > 0 && rate <= 2000)) return { ok: false, message: "Hourly rate must be between 1 and 2,000 USD, or empty." };
  if (!owner || owner.length > 120) return { ok: false, message: "Name the owner who stands behind this number." };
  if (source.length < 3 || source.length > 300) return { ok: false, message: "Say how the number was measured (e.g. “timed 5 manual reviews, Oct 2026”)." };
  const { error } = await ctx.supabase.from("sf_roi_baselines").upsert(
    { workspace_id: ctx.workspace.id, skill, manual_minutes: minutes, hourly_rate_usd: rate, owner, source, set_by: ctx.user.id },
    { onConflict: "workspace_id,skill" });
  if (error) return { ok: false, message: error.message };
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "roi.baseline.set", p_entity_type: "skill", p_entity_id: skill, p_details: { manual_minutes: minutes, hourly_rate_usd: rate, owner, source } });
  revalidatePath("/insights");
  return { ok: true, message: `Baseline saved for ${skill}.` };
}

export async function removeBaseline(fd: FormData): Promise<void> {
  const { skill } = RemoveBaselineForm.parse(fromForm(RemoveBaselineForm, fd));
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") return;
  if (!SKILL.test(skill)) return;
  await ctx.supabase.from("sf_roi_baselines").delete().eq("workspace_id", ctx.workspace.id).eq("skill", skill);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "roi.baseline.remove", p_entity_type: "skill", p_entity_id: skill, p_details: {} });
  revalidatePath("/insights");
}

/** Recompute delivery metrics for every catalog repository now (authors and admins). */
export async function refreshDeliveryNow(): Promise<BaselineResult> {
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin" && ctx.role !== "author") return { ok: false, message: "Authors and administrators refresh delivery metrics." };
  const { refreshDelivery } = await import("@/lib/insights/deliveryRefresh");
  const r = await refreshDelivery(ctx.supabase, ctx.workspace.id, ctx.user.id);
  revalidatePath("/insights");
  return { ok: r.errors.length === 0, message: `${r.ok} repositor${r.ok === 1 ? "y" : "ies"} measured${r.errors.length ? `; ${r.errors.join("; ")}` : ""}.` };
}
