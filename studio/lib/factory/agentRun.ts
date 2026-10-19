/* Server-side agent orchestration: one step per call, state persisted in sf_agent_runs between calls (each call fits
 * the 60 s function limit). Skill steps run the repository skill through the same Python runtime as every other run;
 * compose and approval steps are handled here. Server only. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { skills as repoSkillsData } from "@/lib/data";
import { manifestFromRepoSkill, type RepoSkill } from "./import";
import { executeRun } from "./runtime";
import { getPolicy, type WsCtx } from "./db";
import {
  type AgentSpec, type StepRecord, type StoredInput, type CatalogSkill, isSkill, isCompose, isApproval, stepKind,
  resolveRef, composeFile, parseRef, RefError,
} from "./agents";
import { sha256 } from "./hash";

export type AgentRunStatus = "running" | "awaiting_approval" | "blocked" | "failed" | "succeeded" | "needs_input" | "cancelled";
export interface AgentRunRow {
  id: string; workspace_id: string; agent_version_id: string; invoked_by: string; status: AgentRunStatus;
  inputs: Record<string, StoredInput>; cursor: number; steps: StepRecord[]; cost_usd: number | string | null; error: string | null;
  created_at: string; updated_at: string; finished_at: string | null;
}
export interface AgentRow { id: string; workspace_id: string; slug: string; name: string; description: string; owner_id: string; status: "draft" | "published" | "retired"; created_at: string; updated_at: string }
export interface AgentVersionRow { id: string; agent_id: string; version: number; status: "draft" | "published" | "superseded"; spec: AgentSpec; spec_hash: string; change_note: string; created_by: string; created_at: string; updated_at: string; published_at: string | null }

const REPO = repoSkillsData as unknown as RepoSkill[];

/** The catalog the Builder and validator use: every executable repository skill with its declared inputs and outputs. */
export function agentCatalog(): Map<string, CatalogSkill> {
  return new Map(REPO.filter((s) => s.agent).map((s) => [s.id, {
    id: s.id, name: s.name, stage: (s as unknown as { stage?: string | null }).stage ?? null, description: s.description,
    inputs: s.agent!.inputs.map((i) => ({ name: i.name, type: i.type, required: i.required, from: i.from, default: (i as { default?: string | null }).default ?? null })),
    outputs: s.agent!.outputs.map((o) => o.path),
  }]));
}

const now = () => new Date().toISOString();

/** Month-to-date model spend across skill runs and agent runs vs the workspace budget (null budget = unlimited). */
async function budgetLeft(ctx: WsCtx): Promise<{ ok: boolean; reason: string | null }> {
  const pol = await getPolicy(ctx);
  const budget = pol?.monthly_budget_usd == null ? null : Number(pol.monthly_budget_usd);
  if (budget == null) return { ok: true, reason: null };
  const since = new Date(); since.setUTCDate(1); since.setUTCHours(0, 0, 0, 0);
  const [a, b] = await Promise.all([
    ctx.supabase.from("sf_runs").select("cost_usd").eq("workspace_id", ctx.workspace.id).gte("created_at", since.toISOString()),
    ctx.supabase.from("sf_agent_runs").select("cost_usd").eq("workspace_id", ctx.workspace.id).gte("created_at", since.toISOString()),
  ]);
  const spent = [...(a.data ?? []), ...(b.data ?? [])].reduce((s, r) => s + (r.cost_usd == null ? 0 : Number(r.cost_usd)), 0);
  return spent >= budget ? { ok: false, reason: `monthly budget reached: estimated spend $${spent.toFixed(4)} of $${budget}` } : { ok: true, reason: null };
}

/** Execute the step at run.cursor (or report why it cannot run) and persist the result. Returns the updated row. */
export async function advanceAgentRun(ctx: WsCtx, run: AgentRunRow, spec: AgentSpec): Promise<AgentRunRow> {
  if (run.status !== "running") return run;
  const step = spec.steps[run.cursor];
  const steps = [...run.steps];
  const patch: Partial<AgentRunRow> = {};
  const finish = (status: AgentRunStatus, error: string | null = null) => Object.assign(patch, { status, error, finished_at: now() });

  if (!step) {
    finish("succeeded");
  } else if (isApproval(step)) {
    const prior = steps.find((s) => s.id === step.id);
    if (prior?.status === "approved") patch.cursor = run.cursor + 1;
    else {
      if (!prior) steps.push({ id: step.id, kind: "approval", status: "awaiting_approval", role: step.approval.role, note: step.approval.note ?? "" });
      patch.status = "awaiting_approval";
    }
  } else if (isCompose(step)) {
    const t0 = Date.now();
    try {
      const f = composeFile(step.compose, run.inputs, steps);
      steps.push({ id: step.id, kind: "compose", status: "ok", files: [{ path: f.path, bytes: Buffer.byteLength(f.content), sha256: sha256(f.content), content_text: f.content }], duration_ms: Date.now() - t0 });
      patch.cursor = run.cursor + 1;
    } catch (e) {
      steps.push({ id: step.id, kind: "compose", status: "failed", error: (e as Error).message, duration_ms: Date.now() - t0 });
      finish("failed", `step ${step.id}: ${(e as Error).message}`);
    }
  } else if (isSkill(step)) {
    const repo = REPO.find((s) => s.id === step.skill);
    const m = repo ? manifestFromRepoSkill(repo) : null;
    const rec: StepRecord = { id: step.id, kind: "skill", skill: step.skill, status: "failed" };
    if (!repo || !m || !m.ok) {
      rec.error = `skill ${step.skill} is not available in this deployment`;
    } else {
      const manifest = m.manifest;
      if (spec.config?.provider === "none") manifest.model_config = { ...manifest.model_config, provider: "none" };
      const usesModel = manifest.run.some((r) => r.kind === "llm") && manifest.model_config.provider !== "none";
      const budget = usesModel ? await budgetLeft(ctx) : { ok: true, reason: null };
      try {
        if (!budget.ok) throw new RefError(budget.reason!);
        const optional = new Set(spec.inputs.filter((i) => !i.required).map((i) => i.name));
        const inputs: Record<string, StoredInput> = {};
        for (const [name, ref] of Object.entries(step.inputs ?? {})) {
          const p = parseRef(ref);
          if (p?.kind === "in" && optional.has(p.name) && !run.inputs[p.name]) continue; // optional and not supplied
          inputs[name] = resolveRef(ref, run.inputs, steps);
        }
        const patchRun = await executeRun({
          runId: `${run.id}-${String(run.cursor + 1).padStart(2, "0")}`, manifest, source: { kind: "repo", repo_skill: step.skill }, slug: repo.name,
          files: [], inputs, assumptions: step.assume ?? {}, policy: await getPolicy(ctx),
        });
        const checks = (patchRun.run_json?.checks as { pass?: boolean; check?: string; path?: string; evidence?: unknown }[] | undefined) ?? [];
        const exit = (patchRun.response?.exit_code ?? null) as number | null;
        Object.assign(rec, {
          status: patchRun.status === "succeeded" ? "ok" : patchRun.status === "needs_input" ? "needs_input"
            : step.gate && exit === 1 && patchRun.outputs.length ? "blocked" : "failed",
          checks_passed: checks.filter((c) => c.pass).length, checks_total: checks.length,
          failed_checks: checks.filter((c) => !c.pass).map((c) => ({ check: String(c.check ?? ""), path: String(c.path ?? "").split("/").pop() ?? "", evidence: String(c.evidence ?? "").slice(0, 500) })),
          files: patchRun.outputs.map((o) => ({ path: o.path, bytes: o.bytes, sha256: o.sha256, content_text: o.content_text })),
          error: patchRun.status === "succeeded" ? null : patchRun.error, duration_ms: patchRun.duration_ms,
          cost_usd: patchRun.cost_usd, provider: patchRun.provider, model: patchRun.model,
        } satisfies Partial<StepRecord>);
      } catch (e) {
        rec.error = (e as Error).message;
      }
    }
    steps.push(rec);
    if (rec.status === "ok") patch.cursor = run.cursor + 1;
    else if (rec.status === "blocked") finish("blocked", `step ${step.id}: ${rec.error ?? "gate not met"}`);
    else if (rec.status === "needs_input") finish("needs_input", `step ${step.id}: ${rec.error ?? "missing input"}`);
    else if (step.continue_on_fail) patch.cursor = run.cursor + 1;
    else finish("failed", `step ${step.id}: ${rec.error ?? "failed"}`);
  }
  if (patch.cursor != null && patch.cursor >= spec.steps.length && !patch.status) finish("succeeded");
  patch.steps = steps;
  patch.cost_usd = steps.reduce((s, r) => s + (r.cost_usd ?? 0), 0) || null;
  const { data, error } = await ctx.supabase.from("sf_agent_runs").update(patch).eq("id", run.id).eq("status", "running").select("*").single();
  if (error) throw new Error(`could not save agent run: ${error.message}`);
  return data as AgentRunRow;
}

/** Record an approval for the step the run is waiting on and resume. Reviewers/admins approve (checked by the caller). */
export async function approveAgentRun(sb: SupabaseClient, run: AgentRunRow, user: { id: string; email?: string | null }, note: string): Promise<AgentRunRow> {
  if (run.status !== "awaiting_approval") throw new Error(`run is ${run.status}, not awaiting approval`);
  const steps = run.steps.map((s) => (s.kind === "approval" && s.status === "awaiting_approval"
    ? { ...s, status: "approved" as const, approver_id: user.id, approver_email: user.email ?? "", approval_note: note.slice(0, 1000), at: now() } : s));
  const { data, error } = await sb.from("sf_agent_runs").update({ steps, status: "running" }).eq("id", run.id).eq("status", "awaiting_approval").select("*").single();
  if (error) throw new Error(`could not record approval: ${error.message}`);
  return data as AgentRunRow;
}

export const stepLabel = (spec: AgentSpec, id: string) => {
  const s = spec.steps.find((x) => x.id === id);
  return s ? `${id} · ${stepKind(s)}${isSkill(s) ? ` · ${s.skill}` : ""}` : id;
};
