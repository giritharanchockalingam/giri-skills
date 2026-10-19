/* Self-service actions, the I/O part: load what a skill needs to run on a repository (its form, the repository's
 * folders), and execute an approved action — fetch the repository's real files at the current commit (GitHub App
 * installation token), run the workspace skill through the normal run path (policy, concurrency and budget checks in
 * sf_run_insert), and record the outcome on the action. Server only; runs as the signed-in user (RLS). */
import type { WsCtx, VersionRow } from "@/lib/factory/db";
import { getPolicy, must } from "@/lib/factory/db";
import { githubConfig, installationToken, repoTree, blobText, headSha, type GhRepo } from "@/lib/github/app";
import { validateInputs, describeInputs } from "@/lib/factory/schema";
import { sha256 } from "@/lib/factory/hash";
import { executeRun } from "@/lib/factory/runtime";
import type { TreeFile } from "@/lib/scorecards/checks";
import { fieldsFor, filesUnder, foldersOf, usesModel, checkRequest, gateVerdict, type ActionField, type ActionInput } from "./plan";

type EntityRow = { id: string; key: string; installation_id: number | null; properties: { default_branch?: string; applicable?: { skill: string; input: { name: string; path: string } | null }[] } };
type SkillRow = { id: string; slug: string; name: string; status: string };

const RUNNABLE = ["published", "approved", "in_review", "draft"];

/** The version an action runs: the published one, else (for roles that may run unpublished versions) the newest runnable. */
async function versionFor(ctx: WsCtx, slug: string): Promise<{ skill: SkillRow; version: VersionRow } | null> {
  const { data: skill } = await ctx.supabase.from("sf_skills").select("id, slug, name, status").eq("workspace_id", ctx.workspace.id).eq("slug", slug).maybeSingle<SkillRow>();
  if (!skill) return null;
  const { data: vs } = await ctx.supabase.from("sf_skill_versions").select("*").eq("skill_id", skill.id).order("version", { ascending: false });
  const versions = (vs ?? []) as VersionRow[];
  const pub = versions.find((v) => v.status === "published");
  const any = versions.find((v) => RUNNABLE.includes(v.status));
  const v = pub ?? (ctx.role === "consumer" ? undefined : any);
  return v ? { skill, version: v } : null;
}

async function entity(ctx: WsCtx, id: string) {
  const { data } = await ctx.supabase.from("sf_catalog_entities").select("id, key, installation_id, properties").eq("workspace_id", ctx.workspace.id).eq("kind", "repository").eq("id", id).maybeSingle<EntityRow>();
  return data;
}

async function repoAt(e: EntityRow) {
  const c = githubConfig();
  if (!c.ok) throw new Error("GitHub App not configured.");
  if (!e.installation_id) throw new Error("No GitHub installation for this repository any more.");
  const token = await installationToken(c.cfg, e.installation_id);
  const base = { full_name: e.key, default_branch: e.properties.default_branch ?? "main" } as GhRepo;
  const sha = await headSha(token, base);
  const tree = await repoTree(token, sha ? ({ ...base, default_branch: sha } as GhRepo) : base);
  return { token, sha, tree };
}

/** The workspace skills that can run on repositories (those with a folder input), applicable ones first. */
export async function actionCatalog(ctx: WsCtx, entityId: string): Promise<{ applicable: string[]; skills: { slug: string; name: string; repo_skill: string | null; uses_model: boolean; fields: ActionField[] }[] } | null> {
  const e = await entity(ctx, entityId);
  if (!e) return null;
  const { data } = await ctx.supabase.from("sf_skills").select("slug, name, sf_skill_versions!sf_skill_versions_skill_id_fkey(version, status, manifest, source)").eq("workspace_id", ctx.workspace.id).neq("status", "archived");
  type Row = { slug: string; name: string; sf_skill_versions: { version: number; status: string; manifest: VersionRow["manifest"]; source: VersionRow["source"] }[] };
  const suggested = new Map((e.properties.applicable ?? []).map((a) => [a.skill, a.input]));
  const skills = ((data ?? []) as Row[]).flatMap((s) => {
    const vs = [...s.sf_skill_versions].sort((a, b) => b.version - a.version);
    const v = vs.find((x) => x.status === "published") ?? (ctx.role === "consumer" ? undefined : vs.find((x) => RUNNABLE.includes(x.status)));
    if (!v || !v.manifest.inputs.some((i) => i.type === "dir")) return [];
    const rs = v.source.kind === "repo" ? v.source.repo_skill ?? null : null;
    const hint = rs ? suggested.get(rs) : null;
    return [{ slug: s.slug, name: s.name, repo_skill: rs, uses_model: usesModel(v.manifest), fields: fieldsFor(v.manifest, hint ? { [hint.name]: hint.path || "." } : {}) }];
  });
  const applicable = (e.properties.applicable ?? []).map((a) => a.skill);
  skills.sort((a, b) => Number(!applicable.includes(a.repo_skill ?? "")) - Number(!applicable.includes(b.repo_skill ?? "")) || a.name.localeCompare(b.name));
  return { applicable, skills };
}

/** The repository's folders, for the folder picker. */
export async function repoFolders(ctx: WsCtx, entityId: string): Promise<string[]> {
  const e = await entity(ctx, entityId);
  if (!e) return [];
  const { tree } = await repoAt(e);
  return foldersOf(tree.files);
}

export interface RequestResult { ok: boolean; status?: string; action_id?: string; run_id?: string | null; verdict?: string | null; message: string }


/** Create the request (approval decided in the database from policy), then run it at once if no approval is needed. */
export async function requestAction(ctx: WsCtx, entityId: string, slug: string, given: Record<string, ActionInput>, reason: string): Promise<RequestResult> {
  const e = await entity(ctx, entityId);
  if (!e) return { ok: false, message: "Repository not in this workspace's catalog." };
  const sv = await versionFor(ctx, slug);
  if (!sv) return { ok: false, message: `No runnable version of “${slug}”${ctx.role === "consumer" ? " is published" : ""}.` };
  const fields = fieldsFor(sv.version.manifest);
  if (!fields.some((f) => f.kind === "folder")) return { ok: false, message: "This skill takes no folder, so it cannot run on a repository." };
  let folders: string[];
  try { folders = foldersOf((await repoAt(e)).tree.files); } catch (err) { return { ok: false, message: (err as Error).message }; }
  const problems = checkRequest(fields, given, folders);
  if (problems.length) return { ok: false, message: problems.join("; ") };
  const { data, error } = await ctx.supabase.rpc("sf_action_request", { p_workspace: ctx.workspace.id, p_repo: e.key, p_skill: slug, p_inputs: given, p_uses_model: usesModel(sv.version.manifest), p_reason: reason });
  if (error) return { ok: false, message: error.message };
  const req = data as { id: string; status: string };
  if (req.status === "pending_approval") return { ok: true, status: req.status, action_id: req.id, message: "Waiting for a reviewer's approval (workspace policy). It runs when approved." };
  return runApproved(ctx, req.id);
}

/** Execute an approved action (by its requester right away, or by the approver after approving). */
export async function runApproved(ctx: WsCtx, actionId: string): Promise<RequestResult> {
  const { data: a } = await ctx.supabase.from("sf_action_runs").select("id, entity_id, repo, skill, inputs, status").eq("workspace_id", ctx.workspace.id).eq("id", actionId).maybeSingle<{ id: string; entity_id: string | null; repo: string; skill: string; inputs: Record<string, ActionInput>; status: string }>();
  if (!a) return { ok: false, message: "Action not found." };
  if (a.status !== "approved") return { ok: false, action_id: a.id, status: a.status, message: `This action is ${a.status.replace("_", " ")}.` };
  const fail = async (msg: string, runId: string | null = null) => {
    await ctx.supabase.rpc("sf_action_mark", { p_id: a.id, p_status: "failed", p_run: runId, p_error: msg, p_commit: null });
    return { ok: false, action_id: a.id, status: "failed", run_id: runId, message: msg };
  };
  const e = a.entity_id ? await entity(ctx, a.entity_id) : null;
  const sv = await versionFor(ctx, a.skill);
  let repo: Awaited<ReturnType<typeof repoAt>> | null = null;
  try { if (e) repo = await repoAt(e); } catch (err) { repo = null; void err; }
  const mark = await ctx.supabase.rpc("sf_action_mark", { p_id: a.id, p_status: "running", p_run: null, p_error: null, p_commit: repo?.sha ?? null });
  if (mark.error) return { ok: false, action_id: a.id, message: mark.error.message };
  if (!e || !repo) return fail("The repository could not be read from GitHub.");
  if (!sv) return fail(`No runnable version of “${a.skill}”.`);

  // build the run's inputs from the repository's real files at this commit
  const raw: Record<string, unknown> = {};
  let partial = false;
  const cache = new Map<string, Promise<string | null>>();
  const text = (f: TreeFile) => { if (!cache.has(f.sha)) cache.set(f.sha, blobText(repo!.token, e.key, f.sha)); return cache.get(f.sha)!; };
  for (const f of fieldsFor(sv.version.manifest)) {
    const v = a.inputs[f.name];
    if (!v) continue;
    if (f.kind === "folder" && "folder" in v) {
      const sel = filesUnder(repo.tree.files, v.folder);
      partial ||= sel.partial || repo.tree.truncated;
      const got = await Promise.all(sel.files.map(async (t) => ({ t, c: await text(t) })));
      const files = got.filter((x) => x.c !== null).map((x) => ({ path: sel.strip ? x.t.path.slice(sel.strip.length + 1) : x.t.path, content: x.c as string }));
      if (!files.length) return fail(`No readable files under “${v.folder}”.`);
      raw[f.name] = { kind: "files", files };
    } else if ("text" in v && v.text.trim()) raw[f.name] = v.text;
  }
  const validated = validateInputs(sv.version.manifest, raw);
  if (validated.problems.length || validated.missing.length)
    return fail([...validated.problems.map((p) => `${p.path}: ${p.message}`), ...validated.missing.map((m) => `${m}: missing`)].join("; "));

  const { data: created, error } = await ctx.supabase.rpc("sf_run_insert", { p_version: sv.version.id, p_source: "ui", p_inputs_ref: describeInputs(validated.inputs, sha256), p_idempotency_key: `action-${a.id}` });
  if (error) return fail(error.message);
  const runId = String(created.run_id);
  await ctx.supabase.from("sf_runs").update({ status: "running", started_at: new Date().toISOString() }).eq("id", runId);
  const files = sv.version.source.kind === "authored" ? (must(await ctx.supabase.from("sf_files").select("path, content").eq("version_id", sv.version.id), "files") as { path: string; content: string }[]) : [];
  const patch = await executeRun({ runId, manifest: sv.version.manifest, source: sv.version.source, slug: sv.skill.slug, files, inputs: validated.inputs, assumptions: {}, policy: await getPolicy(ctx), status: sv.version.status });
  const { response, ...row } = patch;
  void response;
  await ctx.supabase.from("sf_runs").update(row).eq("id", runId);
  const note = partial ? " (partial: the folder is larger than the scan limit)" : "";
  const verdict = gateVerdict(row.status, row.run_json);
  const ok = row.status === "succeeded" || verdict !== null;   // a skill's own gate verdict is a result, not a failed action
  const at = `${e.key}${repo.sha ? ` @ ${repo.sha.slice(0, 7)}` : ""}`;
  await ctx.supabase.rpc("sf_action_mark", { p_id: a.id, p_status: ok ? "succeeded" : "failed", p_run: runId, p_error: ok ? (verdict ? `${verdict}${note}` : note || null) : `${row.error ?? row.status}${note}`, p_commit: null });
  return { ok, action_id: a.id, run_id: runId, status: ok ? "succeeded" : "failed", verdict,
    message: !ok ? `The run ${row.status}: ${row.error ?? ""}` : verdict ? `Ran on ${at}. The skill's verdict: ${verdict}${note}. Its report is in the run.` : `Ran on ${at}${note}.` };
}
