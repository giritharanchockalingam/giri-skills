/* Row types for the sf_ tables and the request context (user + selected workspace + role). Server only. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { createServerSupabase } from "@/lib/supabase/server";
import type { Manifest } from "./manifest";
import type { Role } from "./roles";
import type { ReleaseStateRow, VersionStatus } from "./release";

export interface Workspace { id: string; name: string; slug: string; created_by: string; created_at: string }
export interface Membership { id: string; workspace_id: string; user_id: string; role: Role; created_at: string }
export type SkillStatus = "draft" | "published" | "retired";
export interface SkillRow {
  id: string; workspace_id: string; slug: string; name: string; owner_id: string; purpose: string; intended_users: string; usage_guidance: string;
  status: SkillStatus; latest_version_id: string | null; created_at: string; updated_at: string;
}
export interface VersionSource { kind: "repo" | "authored"; repo_skill?: string; /** sha256 of the repo files this version runs (set when it leaves draft) */ content_sha?: string }
export interface VersionRow {
  id: string; skill_id: string; version: number; status: VersionStatus; manifest: Manifest; manifest_hash: string; source: VersionSource;
  change_note: string; created_by: string; created_at: string; updated_at: string; published_at: string | null;
}
export interface FileRow { id: string; version_id: string; path: string; content: string; sha256: string; updated_at: string }
export interface EvalCaseRow { id: string; version_id: string; name: string; inputs: Record<string, unknown>; checks: unknown[]; expected: Record<string, unknown>; notes: string; created_at: string; updated_at: string }
export interface EvalCaseResult { case_id: string; name: string; run_id: string | null; status: string; passed: number; total: number; checks: { check: string; pass: boolean; evidence: string }[]; error: string | null; duration_ms: number }
export interface EvalRunRow {
  id: string; version_id: string; eval_set_hash: string; status: "running" | "finished" | "failed" | "cancelled"; pass_rate: number | string | null;
  results: EvalCaseResult[]; provider: string | null; model: string | null; started_at: string; finished_at: string | null; created_by: string;
}
export interface ApprovalRow { id: string; version_id: string; manifest_hash: string; decision: "approve" | "reject"; note: string; reviewer_id: string; created_at: string }
export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "needs_input" | "timeout" | "cancelled";
export interface RunOutput { path: string; bytes: number; sha256: string; content_text: string | null }
export interface RunRow {
  id: string; workspace_id: string; version_id: string; invoked_by: string | null; api_key_id: string | null; source: "ui" | "api" | "eval"; status: RunStatus;
  idempotency_key: string | null; inputs_ref: unknown[]; run_json: Record<string, unknown> | null; outputs: RunOutput[]; logs: string;
  provider: string | null; model: string | null; usage: Record<string, unknown> | null; cost_usd: number | string | null; cost_is_estimate: boolean;
  started_at: string | null; finished_at: string | null; duration_ms: number | null; error: string | null; created_at: string;
}
export interface ApiKeyRow { id: string; workspace_id: string; name: string; prefix: string; created_by: string; created_at: string; last_used_at: string | null; revoked_at: string | null }
export interface ConnectionRow { id: string; workspace_id: string; kind: string; name: string; config: Record<string, unknown>; secret_ref: string; status: string; created_at: string; updated_at: string }
export interface PolicyRow { workspace_id: string; allowed_tools: string[]; allowed_providers: string[]; monthly_budget_usd: number | string | null; max_concurrency: number; action_approval?: "none" | "model_steps" | "always"; updated_at: string }
export interface AuditRow { id: number; workspace_id: string; actor_id: string | null; actor_kind: string; action: string; entity_type: string; entity_id: string | null; details: Record<string, unknown>; created_at: string }
export type { ReleaseStateRow };

export const WS_COOKIE = "sf_ws";

export interface Ctx {
  supabase: SupabaseClient;
  user: { id: string; email: string | null };
  memberships: (Membership & { workspace: Workspace })[];
  workspace: Workspace | null;
  role: Role | null;
}

/** Signed-in user + selected workspace (cookie sf_ws, else first membership). Redirects to /login when signed out. */
export async function getContext(): Promise<Ctx> {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const { data: rows, error } = await supabase.from("sf_memberships").select("*, workspace:sf_workspaces(*)").order("created_at");
  if (error) throw new Error(error.message);
  const memberships = (rows ?? []) as (Membership & { workspace: Workspace })[];
  const wanted = (await cookies()).get(WS_COOKIE)?.value;
  const m = memberships.find((x) => x.workspace_id === wanted) ?? memberships[0] ?? null;
  return { supabase, user: { id: user.id, email: user.email ?? null }, memberships, workspace: m?.workspace ?? null, role: m?.role ?? null };
}

export type WsCtx = Ctx & { workspace: Workspace; role: Role };
/** Same, but a workspace is required: without one the user is sent to Overview to create or join one. */
export async function requireWorkspace(): Promise<WsCtx> {
  const ctx = await getContext();
  if (!ctx.workspace || !ctx.role) redirect("/");
  return ctx as WsCtx;
}

export function must<T>(r: { data: T | null; error: { message: string } | null }, what = "query"): T {
  if (r.error) throw new Error(`${what}: ${r.error.message}`);
  if (r.data == null) throw new Error(`${what}: not found`);
  return r.data;
}

/* ───────────── common reads ───────────── */

export async function getSkillBySlug(ctx: WsCtx, slug: string): Promise<{ skill: SkillRow; versions: VersionRow[]; states: ReleaseStateRow[] } | null> {
  const { data: skill } = await ctx.supabase.from("sf_skills").select("*").eq("workspace_id", ctx.workspace.id).eq("slug", slug).maybeSingle();
  if (!skill) return null;
  const versions = must(await ctx.supabase.from("sf_skill_versions").select("*").eq("skill_id", skill.id).order("version", { ascending: false }), "versions") as VersionRow[];
  const states = must(await ctx.supabase.from("sf_version_release_state").select("*").eq("skill_id", skill.id), "release state") as ReleaseStateRow[];
  return { skill: skill as SkillRow, versions, states };
}

/** The version a page works on: ?v=<n> if given, else the latest draft/in-review/approved, else the published, else the newest. */
export function pickVersion(versions: VersionRow[], wanted?: string | null): VersionRow | null {
  if (wanted) { const v = versions.find((x) => String(x.version) === wanted); if (v) return v; }
  return versions.find((v) => ["draft", "in_review", "approved"].includes(v.status)) ?? versions.find((v) => v.status === "published") ?? versions[0] ?? null;
}

export async function getPolicy(ctx: WsCtx): Promise<PolicyRow | null> {
  const { data } = await ctx.supabase.from("sf_policies").select("*").eq("workspace_id", ctx.workspace.id).maybeSingle();
  return (data as PolicyRow | null) ?? null;
}

export { fmtDate, fmtMs, fmtUsd } from "./format";
