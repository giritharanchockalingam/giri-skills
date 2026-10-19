"use server";
/* Insights write paths: record a browser run (metadata only), set/remove an ROI baseline (admins). */
import { revalidatePath } from "next/cache";
import { getContext, requireWorkspace } from "@/lib/factory/db";

const SKILL = /^[a-z0-9-]+\/[a-z0-9-]+$/;
const int = (v: unknown, max: number) => (typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= max ? v : null);

/** A skill ran in this browser. Never receives inputs or outputs — only what the dashboard counts. Best effort. */
export async function recordBrowserRun(r: { skill: string; status: string; example: boolean; mode: string | null; checksPassed: number | null; checksTotal: number | null; durationMs: number | null }): Promise<void> {
  try {
    if (!SKILL.test(r.skill) || !["succeeded", "failed", "needs_input"].includes(r.status)) return;
    const ctx = await getContext();
    if (!ctx.workspace) return;
    await ctx.supabase.from("sf_browser_runs").insert({
      workspace_id: ctx.workspace.id, user_id: ctx.user.id, skill: r.skill, status: r.status, example: r.example === true,
      mode: r.mode === "new" || r.mode === "existing" ? r.mode : null,
      checks_passed: int(r.checksPassed, 10_000), checks_total: int(r.checksTotal, 10_000), duration_ms: int(r.durationMs, 3_600_000),
    });
  } catch { /* recording must never break a run */ }
}

export async function saveBaseline(_: unknown, fd: FormData): Promise<{ ok: boolean; message: string }> {
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") return { ok: false, message: "Administrators set ROI baselines." };
  const skill = String(fd.get("skill") ?? "").trim();
  const minutes = Number(fd.get("manual_minutes"));
  const rateRaw = String(fd.get("hourly_rate_usd") ?? "").trim();
  const rate = rateRaw === "" ? null : Number(rateRaw);
  const owner = String(fd.get("owner") ?? "").trim();
  const source = String(fd.get("source") ?? "").trim();
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
  const ctx = await requireWorkspace();
  if (ctx.role !== "admin") return;
  const skill = String(fd.get("skill") ?? "");
  if (!SKILL.test(skill)) return;
  await ctx.supabase.from("sf_roi_baselines").delete().eq("workspace_id", ctx.workspace.id).eq("skill", skill);
  await ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: "roi.baseline.remove", p_entity_type: "skill", p_entity_id: skill, p_details: {} });
  revalidatePath("/insights");
}
