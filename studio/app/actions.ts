"use server";
/* Server actions for the factory UI. Every action re-checks the caller's role (the database enforces it again via
 * RLS and SECURITY DEFINER RPCs); the UI only decides what to show. Each returns {ok, message} for inline feedback. */
import { skillTitle } from "@/lib/names";
import { revalidatePath } from "next/cache";
import { cookies, headers } from "next/headers";
import { adminConfigured, createAdminSupabase } from "@/lib/supabase/server-admin";
import { redirect } from "next/navigation";
import { getContext, requireWorkspace, must, WS_COOKIE, type VersionRow, type SkillRow, type WsCtx } from "@/lib/factory/db";
import { validateManifest, emptyManifest, type Manifest } from "@/lib/factory/manifest";
import { manifestHash, sha256, generateApiKey } from "@/lib/factory/hash";
import { can, isRole, type Action } from "@/lib/factory/roles";
import { manifestFromRepoSkill, casesFromRepoSkill, repoSlug, type RepoSkill } from "@/lib/factory/import";
import { skills as repoSkills } from "@/lib/data";
import { providerKeyPresent, DEFAULT_COMPAT_MODEL } from "@/lib/factory/providers";
import { currentPin } from "@/lib/factory/pins";
import { contractKey } from "@/lib/factory/drift";
import { libraryCasesStale } from "@/lib/factory/libraryContract";
import { ensureSnapshot } from "@/lib/factory/snapshot";
import {
  fromForm, NoFields, EmptyForm, CreateWorkspaceForm, SelectWorkspaceForm, CreateSkillForm, UpdateSkillForm, SaveManifestForm, SaveFileForm, DeleteFileForm,
  CreateDraftForm, UpdateFromLibraryForm, VersionForm, ReviewVersionForm, PublishVersionForm, RetireVersionForm, SaveEvalCaseForm, DeleteEvalCaseForm, ImportFromRepoForm,
  AddMemberForm, RemoveMemberForm, CreateApiKeyForm, RevokeApiKeyForm, SavePolicyForm, SaveConnectionForm, CancelRunForm,
  UpdateDraftsFromLibraryForm, RevokeInvitationForm,
} from "@/lib/validation";

export interface ActionResult { ok: boolean; message: string }
export type ApiKeyResult = ActionResult & { key?: string };
const fail = (message: string): ActionResult => ({ ok: false, message });
const okay = (message: string): ActionResult => ({ ok: true, message });
const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e)).replace(/^[a-z_]+: /, "");

async function guarded(action: Action, fn: (ctx: WsCtx) => Promise<ActionResult>): Promise<ActionResult> {
  try {
    const ctx = await requireWorkspace();
    if (!can(ctx.role, action)) return fail(`Your role (${ctx.role}) cannot do this.`);
    return await fn(ctx);
  } catch (e) {
    if (e && typeof e === "object" && "digest" in e && String((e as { digest: string }).digest).startsWith("NEXT_REDIRECT")) throw e;
    return fail(errMsg(e));
  }
}

const audit = (ctx: WsCtx, action: string, entity_type: string, entity_id: string, details: Record<string, unknown> = {}) =>
  ctx.supabase.rpc("sf_audit", { p_workspace: ctx.workspace.id, p_action: action, p_entity_type: entity_type, p_entity_id: entity_id, p_details: details });

const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "skill";

/* ───────────── workspace ───────────── */

export async function createWorkspace(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const { name } = CreateWorkspaceForm.parse(fromForm(CreateWorkspaceForm, fd));
  try {
    const ctx = await getContext();
    if (!name) return fail("Give the workspace a name.");
    const slug = slugify(name);
    const { data, error } = await ctx.supabase.rpc("sf_create_workspace", { p_name: name, p_slug: slug });
    if (error) return fail(error.message.includes("sf_workspaces_slug_key") ? `A workspace with the slug “${slug}” already exists.` : error.message);
    (await cookies()).set(WS_COOKIE, String(data), { path: "/", sameSite: "lax", httpOnly: true, maxAge: 60 * 60 * 24 * 365 });
  } catch (e) { return fail(errMsg(e)); }
  revalidatePath("/", "layout");
  redirect("/");
}

export async function selectWorkspace(fd: FormData): Promise<void> {
  const { workspace_id: id } = SelectWorkspaceForm.parse(fromForm(SelectWorkspaceForm, fd));
  (await cookies()).set(WS_COOKIE, id, { path: "/", sameSite: "lax", httpOnly: true, maxAge: 60 * 60 * 24 * 365 });
  revalidatePath("/", "layout");
  redirect("/");
}

export async function signOut(form?: FormData): Promise<void> {
  NoFields.parse(form);
  const ctx = await getContext().catch(() => null);
  await ctx?.supabase.auth.signOut();
  redirect("/login");
}

/* ───────────── skills ───────────── */

export async function createSkill(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = CreateSkillForm.parse(fromForm(CreateSkillForm, fd));
  let slug = "";
  const r = await guarded("skill.create", async (ctx) => {
    const name = input.name;
    if (!name) return fail("Give the skill a name.");
    slug = slugify(input.slug || name);
    const base = emptyManifest();
    const manifest: Manifest = { ...base, purpose: input.purpose, intended_users: input.intended_users, usage_guidance: input.usage_guidance,
      outputs: [{ path: "{out}/output.md", checks: ["exists"], schema: null }] };
    const { data: skill, error } = await ctx.supabase.from("sf_skills").insert({
      workspace_id: ctx.workspace.id, slug, name, owner_id: ctx.user.id, purpose: manifest.purpose, intended_users: manifest.intended_users, usage_guidance: manifest.usage_guidance,
    }).select("*").single();
    if (error) return fail(error.message.includes("sf_skills_workspace_id_slug_key") ? `A skill with the slug “${slug}” already exists in this workspace.` : error.message);
    const v = must(await ctx.supabase.from("sf_skill_versions").insert({ skill_id: skill.id, version: 1, manifest, manifest_hash: manifestHash(manifest), source: { kind: "authored" }, created_by: ctx.user.id, change_note: "Created" }).select("*").single(), "version") as VersionRow;
    await ctx.supabase.from("sf_skills").update({ latest_version_id: v.id }).eq("id", skill.id);
    await audit(ctx, "skill.create", "skill", skill.id, { slug, name });
    await audit(ctx, "version.create", "skill_version", v.id, { skill_id: skill.id, version: 1 });
    return okay("Skill created.");
  });
  if (!r.ok) return r;
  revalidatePath("/pipeline");
  redirect(`/skills/${slug}/authoring`);
}

export async function updateSkill(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = UpdateSkillForm.parse(fromForm(UpdateSkillForm, fd));
  return guarded("skill.edit", async (ctx) => {
    const id = input.skill_id;
    const patch = { name: input.name, purpose: input.purpose, intended_users: input.intended_users, usage_guidance: input.usage_guidance };
    if (!patch.name) return fail("Name is required.");
    const { data, error } = await ctx.supabase.from("sf_skills").update(patch).eq("id", id).eq("workspace_id", ctx.workspace.id).select("slug").single();
    if (error) return fail(error.message);
    await audit(ctx, "skill.update", "skill", id, patch);
    revalidatePath(`/skills/${data.slug}`, "layout");
    return okay("Skill details saved.");
  });
}

/** Saves a draft version's manifest (validated + re-hashed). The database rejects this for any non-draft version. */
export async function saveManifest(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = SaveManifestForm.parse(fromForm(SaveManifestForm, fd));
  return guarded("version.edit", async (ctx) => {
    const versionId = input.version_id;
    let raw: unknown;
    try { raw = JSON.parse(input.manifest); } catch (e) { return fail(`Manifest is not valid JSON: ${(e as Error).message}`); }
    const v = validateManifest(raw);
    if (!v.ok) return fail("Manifest has problems: " + v.problems.map((p) => `${p.path}: ${p.message}`).join(" · "));
    const hash = manifestHash(v.manifest);
    const { data: row, error } = await ctx.supabase.from("sf_skill_versions").update({ manifest: v.manifest, manifest_hash: hash, change_note: input.change_note || undefined })
      .eq("id", versionId).select("id, skill_id, version, status, sf_skills!sf_skill_versions_skill_id_fkey(slug)").single();
    if (error) return fail(error.message.includes("immutable") ? "This version is no longer a draft and cannot be edited. Create a new draft version instead." : error.message);
    // the skill's descriptive fields mirror the draft so the catalog stays in step
    await ctx.supabase.from("sf_skills").update({ purpose: v.manifest.purpose, intended_users: v.manifest.intended_users, usage_guidance: v.manifest.usage_guidance }).eq("id", row.skill_id);
    await audit(ctx, "version.update", "skill_version", versionId, { manifest_hash: hash, version: row.version });
    const slug = (row as unknown as { sf_skills: { slug: string } }).sf_skills?.slug;
    if (slug) revalidatePath(`/skills/${slug}`, "layout");
    return okay(`Draft saved (manifest ${hash.slice(0, 12)}…). Any earlier approval of this version is now stale.`);
  });
}

export async function saveFile(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = SaveFileForm.parse(fromForm(SaveFileForm, fd));
  return guarded("version.edit", async (ctx) => {
    const versionId = input.version_id, path = input.path, content = input.content;
    if (!/^(scripts|assets|references)\/[A-Za-z0-9._/-]{1,200}$/.test(path) || path.includes("..")) return fail("Path must be scripts/…, assets/… or references/… (letters, digits, . _ - /).");
    const { error } = await ctx.supabase.from("sf_files").upsert({ version_id: versionId, path, content, sha256: sha256(content) }, { onConflict: "version_id,path" });
    if (error) return fail(error.message.includes("immutable") ? "This version is no longer a draft; its files are frozen." : error.message);
    await audit(ctx, "version.file_save", "skill_version", versionId, { path, sha256: sha256(content) });
    revalidatePath(`/skills/${input.slug}`, "layout");
    return okay(`Saved ${path}.`);
  });
}

export async function deleteFile(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = DeleteFileForm.parse(fromForm(DeleteFileForm, fd));
  return guarded("version.edit", async (ctx) => {
    const versionId = input.version_id, path = input.path;
    const { error } = await ctx.supabase.from("sf_files").delete().eq("version_id", versionId).eq("path", path);
    if (error) return fail(error.message);
    await audit(ctx, "version.file_delete", "skill_version", versionId, { path });
    revalidatePath(`/skills/${input.slug}`, "layout");
    return okay(`Deleted ${path}.`);
  });
}

/** New draft = copy of the chosen version (manifest, files, cases) with version+1. The source version is untouched. */
export async function createDraft(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = CreateDraftForm.parse(fromForm(CreateDraftForm, fd));
  let slug = "", newVersion = 0;
  const r = await guarded("version.create", async (ctx) => {
    const fromId = input.from_version_id;
    const from = must(await ctx.supabase.from("sf_skill_versions").select("*, sf_skills!sf_skill_versions_skill_id_fkey(slug, workspace_id)").eq("id", fromId).single(), "version") as VersionRow & { sf_skills: { slug: string; workspace_id: string } };
    if (from.sf_skills.workspace_id !== ctx.workspace.id) return fail("Not in this workspace.");
    slug = from.sf_skills.slug;
    const { data: maxRow } = await ctx.supabase.from("sf_skill_versions").select("version").eq("skill_id", from.skill_id).order("version", { ascending: false }).limit(1).single();
    newVersion = (maxRow?.version ?? from.version) + 1;
    const nv = must(await ctx.supabase.from("sf_skill_versions").insert({
      skill_id: from.skill_id, version: newVersion, manifest: from.manifest, manifest_hash: from.manifest_hash, source: from.source, created_by: ctx.user.id,
      change_note: input.change_note || `Draft from v${from.version}`,
    }).select("*").single(), "new version") as VersionRow;
    const files = must(await ctx.supabase.from("sf_files").select("path, content, sha256").eq("version_id", fromId), "files") as { path: string; content: string; sha256: string }[];
    if (files.length) { const { error } = await ctx.supabase.from("sf_files").insert(files.map((f) => ({ ...f, version_id: nv.id }))); if (error) return fail(error.message); }
    const cases = must(await ctx.supabase.from("sf_eval_cases").select("name, inputs, checks, expected, notes").eq("version_id", fromId), "cases") as Record<string, unknown>[];
    if (cases.length) { const { error } = await ctx.supabase.from("sf_eval_cases").insert(cases.map((c) => ({ ...c, version_id: nv.id }))); if (error) return fail(error.message); }
    await audit(ctx, "version.create", "skill_version", nv.id, { skill_id: from.skill_id, version: newVersion, from_version: from.version });
    return okay("Draft created.");
  });
  if (!r.ok) return r;
  revalidatePath(`/skills/${slug}`, "layout");
  redirect(`/skills/${slug}/authoring?v=${newVersion}`);
}

/** A new version from the library's current files: its contract, test cases and content pin. Used when the library
 *  changed under a workspace skill (a published version pinned to the old files can no longer run). The previous
 *  version keeps its record; the new one goes through evaluation, approval and publishing like any other. */
/** Brings one workspace skill to the library's current version: updates its draft in place, or creates a new draft
 *  version when the newest is past draft. Returns the version the caller should open. */
async function syncFromLibrary(ctx: WsCtx, skillId: string): Promise<ActionResult & { slug?: string; version?: number }> {
  let slug = "", newVersion = 0;
  const res: ActionResult = await (async () => {
    const skill = must(await ctx.supabase.from("sf_skills").select("*").eq("id", skillId).eq("workspace_id", ctx.workspace.id).single(), "skill") as SkillRow;
    slug = skill.slug;
    const vs = must(await ctx.supabase.from("sf_skill_versions").select("id, version, status, source").eq("skill_id", skill.id).order("version", { ascending: false }), "versions") as Pick<VersionRow, "id" | "version" | "status" | "source">[];
    const repoId = vs.find((v) => v.source?.kind === "repo")?.source.repo_skill;
    const lib = repoId ? (repoSkills as unknown as RepoSkill[]).find((x) => x.id === repoId) : null;
    if (!lib) return fail("This skill is not from the library, or the library no longer has it.");
    const working = vs.find((v) => ["draft", "in_review", "approved"].includes(v.status));
    const pin = currentPin(lib.id);
    const fresh = manifestFromRepoSkill(lib);
    const sameContract = fresh.ok && working ? contractKey(((await ctx.supabase.from("sf_skill_versions").select("manifest").eq("id", working.id).single()).data?.manifest ?? null) as never) === contractKey(fresh.manifest) : false;
    const casesStale = working ? libraryCasesStale(lib.id, ((await ctx.supabase.from("sf_eval_cases").select("name, inputs, checks").eq("version_id", working.id)).data ?? []) as { name: string; inputs: unknown; checks: unknown }[]) : false;
    if (working && working.source?.content_sha === pin && sameContract && !casesStale) return fail(`v${working.version} already matches the library — evaluate and publish it.`);
    if (working && working.status !== "draft") return fail(`v${working.version} is ${working.status.replace("_", " ")}; withdraw it to draft first.`);
    const m = manifestFromRepoSkill(lib);
    if (!m.ok) return fail(`The library version has problems: ${m.problems.map((p) => `${p.path} ${p.message}`).join("; ")}`);
    if (working) {
      // a draft is still being worked on: bring it to the library's files in place. Library cases are brought to the
      // library's current inputs and checks (a stale check would grade the new files against the old contract);
      // cases added here, with names the library does not use, are kept as they are.
      const { error } = await ctx.supabase.from("sf_skill_versions").update({ manifest: m.manifest, manifest_hash: manifestHash(m.manifest), source: { kind: "repo", repo_skill: lib.id, content_sha: pin ?? undefined } }).eq("id", working.id).eq("status", "draft");
      if (error) return fail(error.message);
      const have = new Map(((await ctx.supabase.from("sf_eval_cases").select("id, name").eq("version_id", working.id)).data ?? []).map((c: { id: string; name: string }) => [c.name, c.id]));
      const libCases = casesFromRepoSkill(lib);
      const add = libCases.filter((c) => !have.has(c.name));
      const refresh = libCases.filter((c) => have.has(c.name));
      if (add.length) { const { error: ce } = await ctx.supabase.from("sf_eval_cases").insert(add.map((c) => ({ ...c, version_id: working.id }))); if (ce) return fail(ce.message); }
      for (const c of refresh) {
        const { error: ue } = await ctx.supabase.from("sf_eval_cases").update({ inputs: c.inputs, checks: c.checks, expected: c.expected, notes: c.notes }).eq("id", have.get(c.name)!);
        if (ue) return fail(ue.message);
      }
      await audit(ctx, "version.update_from_library", "skill_version", working.id, { skill_id: skill.id, version: working.version, repo_skill: lib.id, content_sha: pin, cases_added: add.length, cases_refreshed: refresh.length, in_place: true });
      newVersion = working.version;
      return okay(`v${working.version} updated to the library's current files.`);
    }
    newVersion = (vs[0]?.version ?? 0) + 1;
    const prev = vs.find((v) => v.status === "published") ?? vs[0];
    const nv = must(await ctx.supabase.from("sf_skill_versions").insert({
      skill_id: skill.id, version: newVersion, manifest: m.manifest, manifest_hash: manifestHash(m.manifest),
      source: { kind: "repo", repo_skill: lib.id, content_sha: pin ?? undefined }, created_by: ctx.user.id,
      change_note: `Updated from the library (${lib.id}${prev?.source?.content_sha && pin ? `, files ${prev.source.content_sha.slice(0, 8)} → ${pin.slice(0, 8)}` : ""})`,
    }).select("*").single(), "new version") as VersionRow;
    const cases = casesFromRepoSkill(lib);
    if (cases.length) { const { error } = await ctx.supabase.from("sf_eval_cases").insert(cases.map((c) => ({ ...c, version_id: nv.id }))); if (error) return fail(error.message); }
    await ctx.supabase.from("sf_skills").update({ latest_version_id: nv.id }).eq("id", skill.id);
    await audit(ctx, "version.update_from_library", "skill_version", nv.id, { skill_id: skill.id, version: newVersion, repo_skill: lib.id, content_sha: pin, cases: cases.length });
    return okay(`v${newVersion} created from the library.`);
  })();
  return { ...res, slug, version: newVersion };
}

export async function updateFromLibrary(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = UpdateFromLibraryForm.parse(fromForm(UpdateFromLibraryForm, fd));
  const r = await guarded("version.create", (ctx) => syncFromLibrary(ctx, input.skill_id));
  if (!r.ok) return r;
  const { slug, version } = r as ActionResult & { slug?: string; version?: number };
  revalidatePath("/", "layout");
  redirect(`/skills/${slug}/evaluations?v=${version}`);
}

/** Every draft whose library version moved on, updated in place (cases added here are kept). Live versions are not
 *  touched: each needs its own new version, evaluation and approval. */
export async function updateDraftsFromLibrary(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const { skill_ids } = UpdateDraftsFromLibraryForm.parse(fromForm(UpdateDraftsFromLibraryForm, fd));
  const ids = skill_ids.split(",").filter((x) => /^[0-9a-f-]{36}$/.test(x)).slice(0, 200);
  if (!ids.length) return fail("No drafts to update.");
  const r = await guarded("version.create", async (ctx) => {
    const done: string[] = [], problems: string[] = [];
    for (const id of ids) {
      const x = await syncFromLibrary(ctx, id);
      if (x.ok) done.push(x.slug ?? id); else problems.push(`${x.slug || id}: ${x.message}`);
    }
    return problems.length ? { ok: done.length > 0, message: `${done.length} draft(s) updated. Not updated: ${problems.join(" · ")}` } : okay(`${done.length} draft(s) updated to the library. Run their evaluations next.`);
  });
  revalidatePath("/", "layout");
  return r;
}

/* ───────────── lifecycle ───────────── */

export async function requestReview(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = VersionForm.parse(fromForm(VersionForm, fd));
  return guarded("version.request_review", async (ctx) => {
    const id = input.version_id;
    // pin repository files at the moment review is requested: the reviewer approves exactly these files
    const { data: cur } = await ctx.supabase.from("sf_skill_versions").select("source").eq("id", id).maybeSingle();
    const src = (cur?.source ?? { kind: "authored" }) as { kind: string; repo_skill?: string };
    const pin = src.kind === "repo" ? currentPin(src.repo_skill) : null;
    if (src.kind === "repo" && !pin) return fail(`Repository skill ${src.repo_skill} is not in this deployment.`);
    const { error } = await ctx.supabase.from("sf_skill_versions").update(pin ? { status: "in_review", source: { ...src, content_sha: pin } } : { status: "in_review" }).eq("id", id).eq("status", "draft");
    if (error) return fail(error.message);
    await audit(ctx, "version.request_review", "skill_version", id);
    // freeze the reviewed files now, so later library changes never alter (or stop) this version
    let frozenNote = "";
    if (pin) {
      try { frozenNote = (await ensureSnapshot(id)) ? " Its files are frozen with it." : ""; }
      catch (e) { frozenNote = ` Its files could not be frozen yet (${(e as Error).message}); they will be on first run.`; }
    }
    revalidatePath(`/skills/${input.slug}`, "layout"); revalidatePath("/pipeline");
    return okay(`Review requested. A reviewer can now approve or reject this exact version.${frozenNote}`);
  });
}

export async function withdrawReview(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = VersionForm.parse(fromForm(VersionForm, fd));
  return guarded("version.request_review", async (ctx) => {
    const id = input.version_id;
    const { error } = await ctx.supabase.from("sf_skill_versions").update({ status: "draft" }).eq("id", id).eq("status", "in_review");
    if (error) return fail(error.message);
    await audit(ctx, "version.withdraw_review", "skill_version", id);
    revalidatePath(`/skills/${input.slug}`, "layout"); revalidatePath("/pipeline");
    return okay("Back to draft.");
  });
}

/** Approved → draft: the approval row keeps the reviewed hash, so an edit makes it stale and a new review is needed. */
export async function reopenVersion(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = VersionForm.parse(fromForm(VersionForm, fd));
  return guarded("version.edit", async (ctx) => {
    const id = input.version_id;
    const { error } = await ctx.supabase.from("sf_skill_versions").update({ status: "draft" }).eq("id", id).eq("status", "approved");
    if (error) return fail(error.message);
    await audit(ctx, "version.reopen", "skill_version", id);
    revalidatePath(`/skills/${input.slug}`, "layout"); revalidatePath("/pipeline");
    return okay("Reopened as a draft. The approval stays valid only while the manifest is unchanged; editing it will make the approval stale.");
  });
}

export async function reviewVersion(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = ReviewVersionForm.parse(fromForm(ReviewVersionForm, fd));
  return guarded("version.review", async (ctx) => {
    const decision = input.decision;
    const { error } = await ctx.supabase.rpc("sf_review_version", { p_version: input.version_id, p_decision: decision, p_note: input.note });
    if (error) return fail(error.message);
    revalidatePath(`/skills/${input.slug}`, "layout"); revalidatePath("/pipeline"); revalidatePath("/evaluations");
    return okay(decision === "approve" ? "Approved. The approval is pinned to this manifest; any edit makes it stale." : "Rejected and returned to draft.");
  });
}

export async function publishVersion(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = PublishVersionForm.parse(fromForm(PublishVersionForm, fd));
  return guarded("version.publish", async (ctx) => {
    const { error } = await ctx.supabase.rpc("sf_publish_version", { p_version: input.version_id });
    if (error) return fail(error.message);
    revalidatePath("/", "layout");
    return okay("Published. Consumers and the API now run this version; it is immutable.");
  });
}

export async function retireVersion(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = RetireVersionForm.parse(fromForm(RetireVersionForm, fd));
  return guarded("version.retire", async (ctx) => {
    const { error } = await ctx.supabase.rpc("sf_retire_version", { p_version: input.version_id, p_note: input.note });
    if (error) return fail(error.message);
    revalidatePath("/", "layout");
    return okay("Retired. It can no longer be run.");
  });
}

/* ───────────── evaluation cases ───────────── */

export async function saveEvalCase(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = SaveEvalCaseForm.parse(fromForm(SaveEvalCaseForm, fd));
  return guarded("eval.edit", async (ctx) => {
    const versionId = input.version_id, id = input.case_id, name = input.name;
    if (!name) return fail("Give the case a name.");
    let inputs: unknown, checks: unknown;
    try { inputs = JSON.parse(input.inputs || "{}"); } catch (e) { return fail(`Inputs must be a JSON object: ${(e as Error).message}`); }
    try { checks = JSON.parse(input.checks || "[]"); } catch (e) { return fail(`Checks must be a JSON array: ${(e as Error).message}`); }
    if (typeof inputs !== "object" || inputs === null || Array.isArray(inputs)) return fail("Inputs must be a JSON object of name → value.");
    if (!Array.isArray(checks) || checks.length === 0) return fail("Add at least one check (e.g. \"exit:0\", \"exists:result.json\").");
    const row = { version_id: versionId, name, inputs, checks, notes: input.notes, expected: {} };
    const { error } = id ? await ctx.supabase.from("sf_eval_cases").update(row).eq("id", id) : await ctx.supabase.from("sf_eval_cases").insert(row);
    if (error) return fail(error.message);
    await audit(ctx, id ? "eval_case.update" : "eval_case.create", "skill_version", versionId, { name });
    revalidatePath(`/skills/${input.slug}`, "layout");
    return okay(id ? "Case updated. Existing evaluation results are now outdated for this version." : "Case added. Run the evaluation to produce evidence on the new set.");
  });
}

export async function deleteEvalCase(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = DeleteEvalCaseForm.parse(fromForm(DeleteEvalCaseForm, fd));
  return guarded("eval.edit", async (ctx) => {
    const id = input.case_id;
    const { error } = await ctx.supabase.from("sf_eval_cases").delete().eq("id", id);
    if (error) return fail(error.message);
    await audit(ctx, "eval_case.delete", "eval_case", id);
    revalidatePath(`/skills/${input.slug}`, "layout");
    return okay("Case deleted.");
  });
}

/* ───────────── import from repo ───────────── */

export async function importFromRepo(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = ImportFromRepoForm.parse(fromForm(ImportFromRepoForm, fd));
  return guarded("skill.create", async (ctx) => {
    const ids = input.repo_skill.filter((s) => /^[a-z-]+\/[a-z0-9-]+$/.test(s));
    if (!ids.length) return fail("Select at least one repository skill.");
    const { data: existing } = await ctx.supabase.from("sf_skills").select("slug").eq("workspace_id", ctx.workspace.id);
    const taken = new Set((existing ?? []).map((s: { slug: string }) => s.slug));
    const done: string[] = [], problems: string[] = [];
    for (const id of ids) {
      const s = (repoSkills as unknown as RepoSkill[]).find((x) => x.id === id);
      if (!s) { problems.push(`${id}: not in the repository`); continue; }
      const m = manifestFromRepoSkill(s);
      if (!m.ok) { problems.push(`${id}: ${m.problems.map((p) => `${p.path} ${p.message}`).join("; ")}`); continue; }
      const slug = repoSlug(s, taken);
      if (taken.has(slug)) { problems.push(`${id}: already imported as “${slug}”`); continue; }
      const { data: skill, error } = await ctx.supabase.from("sf_skills").insert({
        workspace_id: ctx.workspace.id, slug, name: skillTitle(s.name), owner_id: ctx.user.id, purpose: m.manifest.purpose, intended_users: m.manifest.intended_users, usage_guidance: m.manifest.usage_guidance,
      }).select("*").single();
      if (error) { problems.push(`${id}: ${error.message}`); continue; }
      const { data: v, error: ve } = await ctx.supabase.from("sf_skill_versions").insert({
        skill_id: skill.id, version: 1, manifest: m.manifest, manifest_hash: manifestHash(m.manifest), source: { kind: "repo", repo_skill: s.id, content_sha: currentPin(s.id) ?? undefined }, created_by: ctx.user.id,
        change_note: `Imported from repository skill ${s.id} (SKILL.md v${s.metadata.version ?? "?"})`,
      }).select("*").single();
      if (ve || !v) { problems.push(`${id}: ${ve?.message}`); continue; }
      await ctx.supabase.from("sf_skills").update({ latest_version_id: v.id }).eq("id", skill.id);
      const cases = casesFromRepoSkill(s);
      if (cases.length) {
        const { error: ce } = await ctx.supabase.from("sf_eval_cases").insert(cases.map((c) => ({ ...c, version_id: v.id })));
        if (ce) problems.push(`${id}: cases: ${ce.message}`);
      }
      await audit(ctx, "skill.import", "skill", skill.id, { repo_skill: s.id, slug, version_id: v.id, cases: cases.length });
      taken.add(slug); done.push(slug);
    }
    revalidatePath("/pipeline"); revalidatePath("/pipeline"); revalidatePath("/evaluations");
    const msg = `${done.length} skill(s) imported as drafts${done.length ? ` (${done.join(", ")})` : ""}.`;
    return problems.length ? { ok: done.length > 0, message: `${msg} Problems: ${problems.join(" · ")}` } : okay(msg);
  });
}

/* ───────────── administration ───────────── */

export async function addMember(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = AddMemberForm.parse(fromForm(AddMemberForm, fd));
  return guarded("admin.members", async (ctx) => {
    const email = input.email, role = input.role;
    if (!isRole(role)) return fail("Pick a role.");
    const { data: uid, error } = await ctx.supabase.rpc("sf_user_id_by_email", { p_email: email });
    if (error) return fail(error.message);
    if (!uid) return inviteByEmail(ctx, email.trim().toLowerCase(), role);
    const { error: ie } = await ctx.supabase.from("sf_memberships").upsert({ workspace_id: ctx.workspace.id, user_id: uid, role }, { onConflict: "workspace_id,user_id" });
    if (ie) return fail(ie.message);
    await audit(ctx, "membership.upsert", "user", String(uid), { email, role });
    revalidatePath("/admin");
    return okay(`${email} is now ${role}.`);
  });
}

/** No account yet: record an invitation (accepted when that email signs in) and, when the server holds the Supabase
 *  service key, have Supabase email the invite link. Otherwise the admin shares the sign-in link. */
async function inviteByEmail(ctx: WsCtx, email: string, role: string): Promise<ActionResult> {
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return fail("Enter a valid email.");
  const { error } = await ctx.supabase.from("sf_invitations").insert({ workspace_id: ctx.workspace.id, email, role, invited_by: ctx.user.id });
  if (error) return fail(error.message.includes("duplicate") ? `${email} already has a pending invitation.` : error.message);
  await audit(ctx, "invitation.create", "invitation", email, { email, role });
  const h = await headers();
  const origin = `${h.get("x-forwarded-proto") ?? "https"}://${h.get("x-forwarded-host") ?? h.get("host")}`;
  let sent = false, why = "";
  if (adminConfigured()) {
    const { error: ie } = await createAdminSupabase().auth.admin.inviteUserByEmail(email, { redirectTo: `${origin}/auth/callback?next=/` });
    sent = !ie; why = ie?.message ?? "";
  }
  revalidatePath("/admin");
  return okay(sent ? `Invitation emailed to ${email} (${role}). They join when they accept.`
    : `Invitation recorded for ${email} (${role}). Send them ${origin}/login — they join when they sign in with that email.${why ? ` (Email not sent: ${why})` : ""}`);
}

export async function revokeInvitation(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const { id } = RevokeInvitationForm.parse(fromForm(RevokeInvitationForm, fd));
  if (!/^[0-9a-f-]{36}$/.test(id)) return fail("Unknown invitation.");
  return guarded("admin.members", async (ctx) => {
    const { error } = await ctx.supabase.from("sf_invitations").update({ revoked_at: new Date().toISOString() }).eq("workspace_id", ctx.workspace.id).eq("id", id);
    if (error) return fail(error.message);
    await audit(ctx, "invitation.revoke", "invitation", id);
    revalidatePath("/admin");
    return okay("Invitation revoked.");
  });
}

export async function removeMember(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const { user_id: uid } = RemoveMemberForm.parse(fromForm(RemoveMemberForm, fd));
  return guarded("admin.members", async (ctx) => {
    if (uid === ctx.user.id) return fail("You cannot remove yourself.");
    const { error } = await ctx.supabase.from("sf_memberships").delete().eq("workspace_id", ctx.workspace.id).eq("user_id", uid);
    if (error) return fail(error.message);
    await audit(ctx, "membership.remove", "user", uid);
    revalidatePath("/admin");
    return okay("Member removed.");
  });
}

export async function createApiKey(_: ActionResult | null, fd: FormData): Promise<ApiKeyResult> {
  const { name } = CreateApiKeyForm.parse(fromForm(CreateApiKeyForm, fd));
  return guarded("admin.keys", async (ctx) => {
    if (!name) return fail("Give the key a name (e.g. the application that will use it).");
    const k = generateApiKey();
    const { data, error } = await ctx.supabase.from("sf_api_keys").insert({ workspace_id: ctx.workspace.id, name, key_hash: k.hash, prefix: k.prefix, created_by: ctx.user.id }).select("id").single();
    if (error) return fail(error.message);
    await audit(ctx, "api_key.create", "api_key", data.id, { name, prefix: k.prefix });
    revalidatePath("/admin");
    return { ok: true, message: `Key “${name}” created. Copy it now — it is shown once; only its hash is stored.`, key: k.key } as ActionResult & { key: string };
  });
}

export async function revokeApiKey(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const { key_id: id } = RevokeApiKeyForm.parse(fromForm(RevokeApiKeyForm, fd));
  return guarded("admin.keys", async (ctx) => {
    const { error } = await ctx.supabase.from("sf_api_keys").update({ revoked_at: new Date().toISOString() }).eq("id", id).eq("workspace_id", ctx.workspace.id);
    if (error) return fail(error.message);
    await audit(ctx, "api_key.revoke", "api_key", id);
    revalidatePath("/admin");
    return okay("Key revoked. Requests with it now get 401.");
  });
}

export async function savePolicy(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = SavePolicyForm.parse(fromForm(SavePolicyForm, fd));
  return guarded("admin.policies", async (ctx) => {
    const tools = input.allowed_tools.filter((t) => t === "script" || t === "llm");
    const providers = input.allowed_providers.filter((t) => t === "none" || t === "anthropic" || t === "openai_compat");
    const budgetRaw = input.monthly_budget_usd;
    const budget = budgetRaw === "" ? null : Number(budgetRaw);
    if (budget != null && (!Number.isFinite(budget) || budget < 0)) return fail("Monthly budget must be a non-negative number or empty.");
    const conc = Number(input.max_concurrency);
    if (!Number.isInteger(conc) || conc < 1 || conc > 50) return fail("Max concurrency must be an integer 1–50.");
    const approval = input.action_approval || "model_steps";
    if (!["none", "model_steps", "always"].includes(approval)) return fail("Action approval must be none, model_steps or always.");
    const row = { workspace_id: ctx.workspace.id, allowed_tools: tools, allowed_providers: providers, monthly_budget_usd: budget, max_concurrency: conc, action_approval: approval };
    const { error } = await ctx.supabase.from("sf_policies").upsert(row, { onConflict: "workspace_id" });
    if (error) return fail(error.message);
    await audit(ctx, "policy.update", "workspace", ctx.workspace.id, row);
    revalidatePath("/admin");
    return okay("Policy saved. It applies to the next run.");
  });
}

export async function saveConnection(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const input = SaveConnectionForm.parse(fromForm(SaveConnectionForm, fd));
  return guarded("admin.connections", async (ctx) => {
    const name = input.name, kind = input.kind, secretRef = input.secret_ref.toUpperCase();
    if (!/^[a-z0-9_-]{1,40}$/.test(name)) return fail("Name: lowercase letters, digits, - and _ (this is what manifests reference in `connections`).");
    if (!["llm_provider", "http", "database", "other"].includes(kind)) return fail("Pick a kind.");
    if (secretRef && !/^[A-Z0-9_]{1,64}$/.test(secretRef)) return fail("Secret reference must be an environment variable name (A–Z, 0–9, _).");
    const present = secretRef ? Boolean(process.env[secretRef]) : false;
    const row = { workspace_id: ctx.workspace.id, name, kind, secret_ref: secretRef, config: { base_url: input.base_url }, status: secretRef ? (present ? "configured" : "not_configured") : "unverified" };
    const { error } = await ctx.supabase.from("sf_connections").upsert(row, { onConflict: "workspace_id,name" });
    if (error) return fail(error.message);
    await audit(ctx, "connection.upsert", "connection", name, { kind, secret_ref: secretRef, status: row.status });
    revalidatePath("/admin");
    return okay(`Connection “${name}” saved — ${row.status === "configured" ? `${secretRef} is present on the server.` : secretRef ? `${secretRef} is NOT set on the server; runs needing it will report the provider as unavailable.` : "no secret reference given."}`);
  });
}

export async function cancelRun(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  const { run_id: id } = CancelRunForm.parse(fromForm(CancelRunForm, fd));
  try {
    const ctx = await requireWorkspace();
    const { data, error } = await ctx.supabase.from("sf_runs").update({ status: "cancelled", finished_at: new Date().toISOString(), error: "cancelled by the user before it started" })
      .eq("id", id).eq("workspace_id", ctx.workspace.id).eq("status", "queued").select("id");
    if (error) return fail(error.message);
    if (!data?.length) return fail("Only a queued run can be cancelled; a run that has started executes to completion (synchronous runtime).");
    await audit(ctx, "run.cancel", "run", id);
    revalidatePath(`/runs/${id}`); revalidatePath("/runs");
    return okay("Run cancelled.");
  } catch (e) { return fail(errMsg(e)); }
}

/** Server-side check of a skill row for role gating in pages (not an action; exported for reuse). */
export type { SkillRow };

/** Admin: point every DRAFT that has llm steps at the configured OpenAI-compatible provider (SF_LLM_*), and allow that
 *  provider in the workspace policy. Published/approved versions are untouched (immutable / approval-pinned). */
export async function useCompatForDrafts(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  EmptyForm.parse(fromForm(EmptyForm, fd));
  return guarded("admin.policies", async (ctx) => {
    if (!providerKeyPresent("openai_compat")) return fail("SF_LLM_API_KEY is not set on the server. Add it in Vercel and redeploy first.");
    const model = process.env.SF_LLM_MODEL || DEFAULT_COMPAT_MODEL;
    const { data: rows, error } = await ctx.supabase.from("sf_skill_versions").select("id, version, manifest, sf_skills!sf_skill_versions_skill_id_fkey(slug, workspace_id)").eq("status", "draft");
    if (error) return fail(error.message);
    const drafts = (rows ?? []).filter((r) => (r as unknown as { sf_skills: { workspace_id: string } }).sf_skills?.workspace_id === ctx.workspace.id) as unknown as { id: string; version: number; manifest: Manifest; sf_skills: { slug: string } }[];
    const changed: string[] = [], problems: string[] = [];
    for (const d of drafts) {
      if (!d.manifest.run.some((st) => st.kind === "llm")) continue;
      if (d.manifest.model_config.provider === "openai_compat" && d.manifest.model_config.model === model && d.manifest.model_config.max_tokens >= (Number(process.env.SF_LLM_MAX_TOKENS) || 12000)) continue;
      const maxTokens = Math.min(32000, Math.max(d.manifest.model_config.max_tokens, Number(process.env.SF_LLM_MAX_TOKENS) || 12000));
      const v = validateManifest({ ...d.manifest, model_config: { ...d.manifest.model_config, provider: "openai_compat", model, max_tokens: maxTokens },
        limits: { ...d.manifest.limits, max_tokens: Math.max(d.manifest.limits.max_tokens, maxTokens) } });
      if (!v.ok) { problems.push(`${d.sf_skills.slug}: ${v.problems.map((x) => x.message).join("; ")}`); continue; }
      const hash = manifestHash(v.manifest);
      const { error: ue } = await ctx.supabase.from("sf_skill_versions").update({ manifest: v.manifest, manifest_hash: hash, change_note: `model provider → openai_compat · ${model}` }).eq("id", d.id);
      if (ue) { problems.push(`${d.sf_skills.slug}: ${ue.message}`); continue; }
      await audit(ctx, "version.update", "skill_version", d.id, { manifest_hash: hash, version: d.version, provider: "openai_compat", model });
      changed.push(d.sf_skills.slug);
    }
    const { data: pol } = await ctx.supabase.from("sf_policies").select("*").eq("workspace_id", ctx.workspace.id).maybeSingle();
    const allowed: string[] = (pol?.allowed_providers as string[] | undefined) ?? ["none", "anthropic"];
    if (!allowed.includes("openai_compat")) {
      const row = { workspace_id: ctx.workspace.id, allowed_tools: pol?.allowed_tools ?? ["script", "llm"], allowed_providers: [...allowed, "openai_compat"], monthly_budget_usd: pol?.monthly_budget_usd ?? null, max_concurrency: pol?.max_concurrency ?? 2 };
      const { error: pe } = await ctx.supabase.from("sf_policies").upsert(row, { onConflict: "workspace_id" });
      if (pe) return fail(pe.message);
      await audit(ctx, "policy.update", "workspace", ctx.workspace.id, row);
    }
    revalidatePath("/", "layout");
    const msg = changed.length ? `${changed.length} draft(s) now use ${model}: ${changed.join(", ")}.` : `No drafts needed a change (all llm drafts already use ${model}).`;
    return problems.length ? fail(`${msg} Not changed: ${problems.join(" · ")}`) : okay(msg);
  });
}
