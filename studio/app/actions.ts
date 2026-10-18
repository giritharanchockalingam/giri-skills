"use server";
/* Server actions for the factory UI. Every action re-checks the caller's role (the database enforces it again via
 * RLS and SECURITY DEFINER RPCs); the UI only decides what to show. Each returns {ok, message} for inline feedback. */
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getContext, requireWorkspace, must, WS_COOKIE, type VersionRow, type SkillRow, type WsCtx } from "@/lib/factory/db";
import { validateManifest, emptyManifest, type Manifest } from "@/lib/factory/manifest";
import { manifestHash, sha256, generateApiKey } from "@/lib/factory/hash";
import { can, isRole, type Action } from "@/lib/factory/roles";
import { manifestFromRepoSkill, casesFromRepoSkill, repoSlug, type RepoSkill } from "@/lib/factory/import";
import { skills as repoSkills } from "@/lib/data";

export interface ActionResult { ok: boolean; message: string }
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

const str = (fd: FormData, k: string, max = 10000) => String(fd.get(k) ?? "").slice(0, max).trim();
const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "skill";

/* ───────────── workspace ───────────── */

export async function createWorkspace(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  try {
    const ctx = await getContext();
    const name = str(fd, "name", 120);
    if (!name) return fail("Give the workspace a name.");
    const slug = slugify(name);
    const { data, error } = await ctx.supabase.rpc("sf_create_workspace", { p_name: name, p_slug: slug });
    if (error) return fail(error.message.includes("sf_workspaces_slug_key") ? `A workspace with the slug “${slug}” already exists.` : error.message);
    (await cookies()).set(WS_COOKIE, String(data), { path: "/", sameSite: "lax", httpOnly: true, maxAge: 60 * 60 * 24 * 365 });
  } catch (e) { return fail(errMsg(e)); }
  revalidatePath("/", "layout");
  redirect("/overview");
}

export async function selectWorkspace(fd: FormData): Promise<void> {
  const id = str(fd, "workspace_id", 64);
  (await cookies()).set(WS_COOKIE, id, { path: "/", sameSite: "lax", httpOnly: true, maxAge: 60 * 60 * 24 * 365 });
  revalidatePath("/", "layout");
  redirect("/overview");
}

export async function signOut(): Promise<void> {
  const ctx = await getContext().catch(() => null);
  await ctx?.supabase.auth.signOut();
  redirect("/login");
}

/* ───────────── skills ───────────── */

export async function createSkill(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  let slug = "";
  const r = await guarded("skill.create", async (ctx) => {
    const name = str(fd, "name", 160);
    if (!name) return fail("Give the skill a name.");
    slug = slugify(str(fd, "slug", 80) || name);
    const base = emptyManifest();
    const manifest: Manifest = { ...base, purpose: str(fd, "purpose", 2000), intended_users: str(fd, "intended_users", 2000), usage_guidance: str(fd, "usage_guidance", 4000),
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
  revalidatePath("/");
  redirect(`/skills/${slug}/authoring`);
}

export async function updateSkill(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("skill.edit", async (ctx) => {
    const id = str(fd, "skill_id", 64);
    const patch = { name: str(fd, "name", 160), purpose: str(fd, "purpose", 2000), intended_users: str(fd, "intended_users", 2000), usage_guidance: str(fd, "usage_guidance", 4000) };
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
  return guarded("version.edit", async (ctx) => {
    const versionId = str(fd, "version_id", 64);
    let raw: unknown;
    try { raw = JSON.parse(str(fd, "manifest", 500_000)); } catch (e) { return fail(`Manifest is not valid JSON: ${(e as Error).message}`); }
    const v = validateManifest(raw);
    if (!v.ok) return fail("Manifest has problems: " + v.problems.map((p) => `${p.path}: ${p.message}`).join(" · "));
    const hash = manifestHash(v.manifest);
    const { data: row, error } = await ctx.supabase.from("sf_skill_versions").update({ manifest: v.manifest, manifest_hash: hash, change_note: str(fd, "change_note", 500) || undefined })
      .eq("id", versionId).select("id, skill_id, version, status, sf_skills(slug)").single();
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
  return guarded("version.edit", async (ctx) => {
    const versionId = str(fd, "version_id", 64), path = str(fd, "path", 220), content = String(fd.get("content") ?? "").slice(0, 400_000);
    if (!/^(scripts|assets|references)\/[A-Za-z0-9._/-]{1,200}$/.test(path) || path.includes("..")) return fail("Path must be scripts/…, assets/… or references/… (letters, digits, . _ - /).");
    const { error } = await ctx.supabase.from("sf_files").upsert({ version_id: versionId, path, content, sha256: sha256(content) }, { onConflict: "version_id,path" });
    if (error) return fail(error.message.includes("immutable") ? "This version is no longer a draft; its files are frozen." : error.message);
    await audit(ctx, "version.file_save", "skill_version", versionId, { path, sha256: sha256(content) });
    revalidatePath(`/skills/${str(fd, "slug", 80)}`, "layout");
    return okay(`Saved ${path}.`);
  });
}

export async function deleteFile(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("version.edit", async (ctx) => {
    const versionId = str(fd, "version_id", 64), path = str(fd, "path", 220);
    const { error } = await ctx.supabase.from("sf_files").delete().eq("version_id", versionId).eq("path", path);
    if (error) return fail(error.message);
    await audit(ctx, "version.file_delete", "skill_version", versionId, { path });
    revalidatePath(`/skills/${str(fd, "slug", 80)}`, "layout");
    return okay(`Deleted ${path}.`);
  });
}

/** New draft = copy of the chosen version (manifest, files, cases) with version+1. The source version is untouched. */
export async function createDraft(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  let slug = "", newVersion = 0;
  const r = await guarded("version.create", async (ctx) => {
    const fromId = str(fd, "from_version_id", 64);
    const from = must(await ctx.supabase.from("sf_skill_versions").select("*, sf_skills(slug, workspace_id)").eq("id", fromId).single(), "version") as VersionRow & { sf_skills: { slug: string; workspace_id: string } };
    if (from.sf_skills.workspace_id !== ctx.workspace.id) return fail("Not in this workspace.");
    slug = from.sf_skills.slug;
    const { data: maxRow } = await ctx.supabase.from("sf_skill_versions").select("version").eq("skill_id", from.skill_id).order("version", { ascending: false }).limit(1).single();
    newVersion = (maxRow?.version ?? from.version) + 1;
    const nv = must(await ctx.supabase.from("sf_skill_versions").insert({
      skill_id: from.skill_id, version: newVersion, manifest: from.manifest, manifest_hash: from.manifest_hash, source: from.source, created_by: ctx.user.id,
      change_note: str(fd, "change_note", 500) || `Draft from v${from.version}`,
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

/* ───────────── lifecycle ───────────── */

export async function requestReview(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("version.request_review", async (ctx) => {
    const id = str(fd, "version_id", 64);
    const { error } = await ctx.supabase.from("sf_skill_versions").update({ status: "in_review" }).eq("id", id).eq("status", "draft");
    if (error) return fail(error.message);
    await audit(ctx, "version.request_review", "skill_version", id);
    revalidatePath(`/skills/${str(fd, "slug", 80)}`, "layout"); revalidatePath("/overview");
    return okay("Review requested. A reviewer can now approve or reject this exact version.");
  });
}

export async function withdrawReview(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("version.request_review", async (ctx) => {
    const id = str(fd, "version_id", 64);
    const { error } = await ctx.supabase.from("sf_skill_versions").update({ status: "draft" }).eq("id", id).eq("status", "in_review");
    if (error) return fail(error.message);
    await audit(ctx, "version.withdraw_review", "skill_version", id);
    revalidatePath(`/skills/${str(fd, "slug", 80)}`, "layout"); revalidatePath("/overview");
    return okay("Back to draft.");
  });
}

/** Approved → draft: the approval row keeps the reviewed hash, so an edit makes it stale and a new review is needed. */
export async function reopenVersion(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("version.edit", async (ctx) => {
    const id = str(fd, "version_id", 64);
    const { error } = await ctx.supabase.from("sf_skill_versions").update({ status: "draft" }).eq("id", id).eq("status", "approved");
    if (error) return fail(error.message);
    await audit(ctx, "version.reopen", "skill_version", id);
    revalidatePath(`/skills/${str(fd, "slug", 80)}`, "layout"); revalidatePath("/overview");
    return okay("Reopened as a draft. The approval stays valid only while the manifest is unchanged; editing it will make the approval stale.");
  });
}

export async function reviewVersion(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("version.review", async (ctx) => {
    const decision = str(fd, "decision", 10);
    const { error } = await ctx.supabase.rpc("sf_review_version", { p_version: str(fd, "version_id", 64), p_decision: decision, p_note: str(fd, "note", 2000) });
    if (error) return fail(error.message);
    revalidatePath(`/skills/${str(fd, "slug", 80)}`, "layout"); revalidatePath("/overview"); revalidatePath("/evaluations");
    return okay(decision === "approve" ? "Approved. The approval is pinned to this manifest; any edit makes it stale." : "Rejected and returned to draft.");
  });
}

export async function publishVersion(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("version.publish", async (ctx) => {
    const { error } = await ctx.supabase.rpc("sf_publish_version", { p_version: str(fd, "version_id", 64) });
    if (error) return fail(error.message);
    revalidatePath("/", "layout");
    return okay("Published. Consumers and the API now run this version; it is immutable.");
  });
}

export async function retireVersion(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("version.retire", async (ctx) => {
    const { error } = await ctx.supabase.rpc("sf_retire_version", { p_version: str(fd, "version_id", 64), p_note: str(fd, "note", 500) });
    if (error) return fail(error.message);
    revalidatePath("/", "layout");
    return okay("Retired. It can no longer be run.");
  });
}

/* ───────────── evaluation cases ───────────── */

export async function saveEvalCase(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("eval.edit", async (ctx) => {
    const versionId = str(fd, "version_id", 64), id = str(fd, "case_id", 64), name = str(fd, "name", 160);
    if (!name) return fail("Give the case a name.");
    let inputs: unknown, checks: unknown;
    try { inputs = JSON.parse(str(fd, "inputs", 200_000) || "{}"); } catch (e) { return fail(`Inputs must be a JSON object: ${(e as Error).message}`); }
    try { checks = JSON.parse(str(fd, "checks", 20_000) || "[]"); } catch (e) { return fail(`Checks must be a JSON array: ${(e as Error).message}`); }
    if (typeof inputs !== "object" || inputs === null || Array.isArray(inputs)) return fail("Inputs must be a JSON object of name → value.");
    if (!Array.isArray(checks) || checks.length === 0) return fail("Add at least one check (e.g. \"exit:0\", \"exists:result.json\").");
    const row = { version_id: versionId, name, inputs, checks, notes: str(fd, "notes", 4000), expected: {} };
    const { error } = id ? await ctx.supabase.from("sf_eval_cases").update(row).eq("id", id) : await ctx.supabase.from("sf_eval_cases").insert(row);
    if (error) return fail(error.message);
    await audit(ctx, id ? "eval_case.update" : "eval_case.create", "skill_version", versionId, { name });
    revalidatePath(`/skills/${str(fd, "slug", 80)}`, "layout");
    return okay(id ? "Case updated. Existing evaluation results are now outdated for this version." : "Case added. Run the evaluation to produce evidence on the new set.");
  });
}

export async function deleteEvalCase(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("eval.edit", async (ctx) => {
    const id = str(fd, "case_id", 64);
    const { error } = await ctx.supabase.from("sf_eval_cases").delete().eq("id", id);
    if (error) return fail(error.message);
    await audit(ctx, "eval_case.delete", "eval_case", id);
    revalidatePath(`/skills/${str(fd, "slug", 80)}`, "layout");
    return okay("Case deleted.");
  });
}

/* ───────────── import from repo ───────────── */

export async function importFromRepo(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("skill.create", async (ctx) => {
    const ids = fd.getAll("repo_skill").map(String).filter((s) => /^[a-z-]+\/[a-z0-9-]+$/.test(s));
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
        workspace_id: ctx.workspace.id, slug, name: s.name, owner_id: ctx.user.id, purpose: m.manifest.purpose, intended_users: m.manifest.intended_users, usage_guidance: m.manifest.usage_guidance,
      }).select("*").single();
      if (error) { problems.push(`${id}: ${error.message}`); continue; }
      const { data: v, error: ve } = await ctx.supabase.from("sf_skill_versions").insert({
        skill_id: skill.id, version: 1, manifest: m.manifest, manifest_hash: manifestHash(m.manifest), source: { kind: "repo", repo_skill: s.id }, created_by: ctx.user.id,
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
    revalidatePath("/"); revalidatePath("/overview"); revalidatePath("/evaluations");
    const msg = `${done.length} skill(s) imported as drafts${done.length ? ` (${done.join(", ")})` : ""}.`;
    return problems.length ? { ok: done.length > 0, message: `${msg} Problems: ${problems.join(" · ")}` } : okay(msg);
  });
}

/* ───────────── administration ───────────── */

export async function addMember(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("admin.members", async (ctx) => {
    const email = str(fd, "email", 200), role = str(fd, "role", 20);
    if (!isRole(role)) return fail("Pick a role.");
    const { data: uid, error } = await ctx.supabase.rpc("sf_user_id_by_email", { p_email: email });
    if (error) return fail(error.message);
    if (!uid) return fail(`No account with the email ${email}. The person must sign up at /login first.`);
    const { error: ie } = await ctx.supabase.from("sf_memberships").upsert({ workspace_id: ctx.workspace.id, user_id: uid, role }, { onConflict: "workspace_id,user_id" });
    if (ie) return fail(ie.message);
    await audit(ctx, "membership.upsert", "user", String(uid), { email, role });
    revalidatePath("/admin");
    return okay(`${email} is now ${role}.`);
  });
}

export async function removeMember(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("admin.members", async (ctx) => {
    const uid = str(fd, "user_id", 64);
    if (uid === ctx.user.id) return fail("You cannot remove yourself.");
    const { error } = await ctx.supabase.from("sf_memberships").delete().eq("workspace_id", ctx.workspace.id).eq("user_id", uid);
    if (error) return fail(error.message);
    await audit(ctx, "membership.remove", "user", uid);
    revalidatePath("/admin");
    return okay("Member removed.");
  });
}

export async function createApiKey(_: ActionResult | null, fd: FormData): Promise<ActionResult & { key?: string }> {
  return guarded("admin.keys", async (ctx) => {
    const name = str(fd, "name", 80);
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
  return guarded("admin.keys", async (ctx) => {
    const id = str(fd, "key_id", 64);
    const { error } = await ctx.supabase.from("sf_api_keys").update({ revoked_at: new Date().toISOString() }).eq("id", id).eq("workspace_id", ctx.workspace.id);
    if (error) return fail(error.message);
    await audit(ctx, "api_key.revoke", "api_key", id);
    revalidatePath("/admin");
    return okay("Key revoked. Requests with it now get 401.");
  });
}

export async function savePolicy(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("admin.policies", async (ctx) => {
    const tools = fd.getAll("allowed_tools").map(String).filter((t) => t === "script" || t === "llm");
    const providers = fd.getAll("allowed_providers").map(String).filter((t) => t === "none" || t === "anthropic");
    const budgetRaw = str(fd, "monthly_budget_usd", 20);
    const budget = budgetRaw === "" ? null : Number(budgetRaw);
    if (budget != null && (!Number.isFinite(budget) || budget < 0)) return fail("Monthly budget must be a non-negative number or empty.");
    const conc = Number(str(fd, "max_concurrency", 5));
    if (!Number.isInteger(conc) || conc < 1 || conc > 50) return fail("Max concurrency must be an integer 1–50.");
    const row = { workspace_id: ctx.workspace.id, allowed_tools: tools, allowed_providers: providers, monthly_budget_usd: budget, max_concurrency: conc };
    const { error } = await ctx.supabase.from("sf_policies").upsert(row, { onConflict: "workspace_id" });
    if (error) return fail(error.message);
    await audit(ctx, "policy.update", "workspace", ctx.workspace.id, row);
    revalidatePath("/admin");
    return okay("Policy saved. It applies to the next run.");
  });
}

export async function saveConnection(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  return guarded("admin.connections", async (ctx) => {
    const name = str(fd, "name", 80), kind = str(fd, "kind", 20), secretRef = str(fd, "secret_ref", 64).toUpperCase();
    if (!/^[a-z0-9_-]{1,40}$/.test(name)) return fail("Name: lowercase letters, digits, - and _ (this is what manifests reference in `connections`).");
    if (!["llm_provider", "http", "database", "other"].includes(kind)) return fail("Pick a kind.");
    if (secretRef && !/^[A-Z0-9_]{1,64}$/.test(secretRef)) return fail("Secret reference must be an environment variable name (A–Z, 0–9, _).");
    const present = secretRef ? Boolean(process.env[secretRef]) : false;
    const row = { workspace_id: ctx.workspace.id, name, kind, secret_ref: secretRef, config: { base_url: str(fd, "base_url", 300) }, status: secretRef ? (present ? "configured" : "not_configured") : "unverified" };
    const { error } = await ctx.supabase.from("sf_connections").upsert(row, { onConflict: "workspace_id,name" });
    if (error) return fail(error.message);
    await audit(ctx, "connection.upsert", "connection", name, { kind, secret_ref: secretRef, status: row.status });
    revalidatePath("/admin");
    return okay(`Connection “${name}” saved — ${row.status === "configured" ? `${secretRef} is present on the server.` : secretRef ? `${secretRef} is NOT set on the server; runs needing it will report the provider as unavailable.` : "no secret reference given."}`);
  });
}

export async function cancelRun(_: ActionResult | null, fd: FormData): Promise<ActionResult> {
  try {
    const ctx = await requireWorkspace();
    const id = str(fd, "run_id", 64);
    const { data, error } = await ctx.supabase.from("sf_runs").update({ status: "cancelled", finished_at: new Date().toISOString(), error: "cancelled by the user before it started" })
      .eq("id", id).eq("workspace_id", ctx.workspace.id).eq("status", "queued").select("id");
    if (error) return fail(error.message);
    if (!data?.length) return fail("Only a queued run can be cancelled; a run that has started executes to completion (synchronous runtime).");
    await audit(ctx, "run.cancel", "run", id);
    revalidatePath(`/runs/${id}`); revalidatePath("/activity");
    return okay("Run cancelled.");
  } catch (e) { return fail(errMsg(e)); }
}

/** Server-side check of a skill row for role gating in pages (not an action; exported for reuse). */
export type { SkillRow };
