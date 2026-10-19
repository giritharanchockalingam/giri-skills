/* Data access for workspace skills, their versions, files, evaluation cases/runs and approvals. Queries run as the signed-in user. */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { ApprovalRow, EvalCaseRow, EvalRunRow, FileRow, ReleaseStateRow, SkillRow, VersionRow } from "@/lib/factory/db";

export type SkillStatusSummary = Pick<SkillRow, "slug" | "name" | "status">;
export type SkillListItem = Pick<SkillRow, "id" | "slug" | "name" | "status">;
export type EvaluationState = ReleaseStateRow & { skill_id: string; version: number };
export type VersionSummary = Pick<VersionRow, "id" | "skill_id" | "version" | "status" | "source" | "updated_at">;
export type PipelineState = Pick<ReleaseStateRow, "version_id" | "status" | "latest_eval_pass_rate" | "eval_current" | "approval_valid" | "approval_stale" | "publishable" | "eval_case_count">;
export type FileListItem = Pick<FileRow, "path" | "content" | "sha256" | "updated_at">;

/** Slug, name and status of every skill of the workspace. */
export async function listSkillStatuses(sb: SupabaseClient, workspaceId: string): Promise<SkillStatusSummary[] | null> {
  const { data } = await sb.from("sf_skills").select("slug, name, status").eq("workspace_id", workspaceId);
  return data as SkillStatusSummary[] | null;
}

/** The evaluations overview: the workspace's skills and the release state of every live (non-retired) version. */
export async function loadEvaluationsOverview(sb: SupabaseClient, workspaceId: string): Promise<{ skills: SkillListItem[]; states: EvaluationState[] }> {
  const [skillsQ, statesQ] = await Promise.all([
    sb.from("sf_skills").select("id, slug, name, status").eq("workspace_id", workspaceId),
    sb.from("sf_version_release_state").select("*").eq("workspace_id", workspaceId).in("status", ["draft", "in_review", "approved", "published"]),
  ]);
  return { skills: (skillsQ.data ?? []) as SkillListItem[], states: (statesQ.data ?? []) as EvaluationState[] };
}

/** The skills pipeline: every skill (most recently updated first), all visible versions and their release states. */
export async function loadPipeline(sb: SupabaseClient, workspaceId: string): Promise<{ skills: SkillRow[]; versions: VersionSummary[]; states: PipelineState[] }> {
  const [skillsQ, versionsQ, statesQ] = await Promise.all([
    sb.from("sf_skills").select("*").eq("workspace_id", workspaceId).order("updated_at", { ascending: false }),
    sb.from("sf_skill_versions").select("id, skill_id, version, status, source, updated_at").order("version", { ascending: false }),
    sb.from("sf_version_release_state").select("version_id, skill_id, status, latest_eval_pass_rate, eval_current, approval_valid, approval_stale, publishable, eval_case_count").eq("workspace_id", workspaceId),
  ]);
  return { skills: (skillsQ.data ?? []) as SkillRow[], versions: (versionsQ.data ?? []) as VersionSummary[], states: (statesQ.data ?? []) as PipelineState[] };
}

/** A version's evaluation cases (oldest first) and its 10 most recent evaluation runs. */
export async function loadVersionEvaluations(sb: SupabaseClient, versionId: string): Promise<{ cases: EvalCaseRow[]; runs: EvalRunRow[] }> {
  const [casesQ, runsQ] = await Promise.all([
    sb.from("sf_eval_cases").select("*").eq("version_id", versionId).order("created_at"),
    sb.from("sf_eval_runs").select("*").eq("version_id", versionId).order("started_at", { ascending: false }).limit(10),
  ]);
  return { cases: (casesQ.data ?? []) as EvalCaseRow[], runs: (runsQ.data ?? []) as EvalRunRow[] };
}

/** The files packaged with a version, by path. */
export async function listVersionFiles(sb: SupabaseClient, versionId: string): Promise<FileListItem[] | null> {
  const { data } = await sb.from("sf_files").select("path, content, sha256, updated_at").eq("version_id", versionId).order("path");
  return data as FileListItem[] | null;
}

/** A version's approvals, newest first. */
export async function listVersionApprovals(sb: SupabaseClient, versionId: string): Promise<ApprovalRow[]> {
  const { data } = await sb.from("sf_approvals").select("*").eq("version_id", versionId).order("created_at", { ascending: false });
  return (data ?? []) as ApprovalRow[];
}
