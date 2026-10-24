/* WP4 — the server side of "run a governed skill on a PR" and of the run evidence (spec §4.3, §5.3, §7 steps 2–3).
 *  - resolveRepoRun: Port repository entity → GitHub owner/repo (from the entity's url) → the factory's GitHub App
 *    installation for that repo (catalog) → the PR's diff, head commit and URL. The diff becomes the skill's `diff` input
 *    only when the published skill declares one; nothing else is guessed.
 *  - recordRunInPort: one `sf_skill_run` entity per Port-started factory run, related to the skill, the repository and
 *    (when Port knows the e-mail as a user) who triggered it. Deterministic identifier (run_<factory run id>), so a
 *    retry upserts the same entity. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { PortClient } from "./client";
import { REPOSITORY_BLUEPRINT_ID, RUN_BLUEPRINT_ID, SKILL_RUN_BLUEPRINT, runEntity, type RunForPort } from "./map";
import { githubConfig, installationToken, gh } from "@/lib/github/app";

const MAX_DIFF_BYTES = 900_000;   // stays under Port's / the factory's 1 MiB body caps with room for the envelope

export interface RepoRunContext { fullName: string; pr: number; headSha: string; prUrl: string; title: string; diff: string }
export type RepoRunResult = { ok: true; ctx: RepoRunContext } | { ok: false; status: number; message: string };

/** `<owner>/<repo>` from a GitHub URL, or null. */
export const fullNameFromUrl = (url: unknown): string | null => {
  const m = typeof url === "string" ? url.match(/github\.com\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?\/?$/) : null;
  return m ? `${m[1]}/${m[2]}` : null;
};

export async function resolveRepoRun(deps: { port: PortClient; admin: SupabaseClient; workspaceId: string; f?: typeof fetch }, target: string, pr: number): Promise<RepoRunResult> {
  const entity = await deps.port.getEntity(REPOSITORY_BLUEPRINT_ID, target);
  if (!entity) return { ok: false, status: 404, message: `Port has no ${REPOSITORY_BLUEPRINT_ID} entity “${target}”` };
  const fullName = fullNameFromUrl((entity.properties as Record<string, unknown> | undefined)?.url);
  if (!fullName) return { ok: false, status: 422, message: `Port repository “${target}” has no GitHub URL` };

  const { data: repo } = await deps.admin.from("sf_catalog_entities").select("installation_id").eq("workspace_id", deps.workspaceId).eq("kind", "repository").ilike("key", fullName).eq("archived", false).maybeSingle();
  const installationId = (repo as { installation_id: number | null } | null)?.installation_id ?? null;
  if (!installationId) return { ok: false, status: 409, message: `${fullName} is not in this workspace's catalog through the GitHub App; connect it on Integrations → GitHub first` };
  const c = githubConfig();
  if (!c.ok) return { ok: false, status: 503, message: `GitHub App is not configured: ${c.missing.join(", ")}` };

  try {
    const token = await installationToken(c.cfg, installationId, deps.f);
    const auth = `Bearer ${token}`;
    const meta = await gh<{ head: { sha: string }; html_url: string; title: string; state: string }>(`/repos/${fullName}/pulls/${pr}`, auth, { fetchImpl: deps.f });
    const diff = (await gh<string>(`/repos/${fullName}/pulls/${pr}`, auth, { accept: "application/vnd.github.diff", fetchImpl: deps.f })).data;
    if (Buffer.byteLength(diff, "utf8") > MAX_DIFF_BYTES) return { ok: false, status: 413, message: `PR #${pr} diff is larger than ${Math.round(MAX_DIFF_BYTES / 1000)} kB; review it in the factory directly` };
    return { ok: true, ctx: { fullName, pr, headSha: meta.data.head.sha, prUrl: meta.data.html_url, title: meta.data.title, diff } };
  } catch (e) {
    const status = (e as { status?: number }).status;
    return { ok: false, status: status === 404 ? 404 : 502, message: (e as Error).message };
  }
}

/** Does the published version of `slug` declare an input named `name`? (the PR diff only fills a declared input) */
export async function declaresInput(admin: SupabaseClient, workspaceId: string, slug: string, name: string): Promise<boolean> {
  const { data: skill } = await admin.from("sf_skills").select("id").eq("workspace_id", workspaceId).eq("slug", slug).eq("status", "published").maybeSingle();
  if (!skill) return false;
  const { data: v } = await admin.from("sf_skill_versions").select("manifest").eq("skill_id", (skill as { id: string }).id).eq("status", "published").maybeSingle();
  const inputs = ((v as { manifest?: { inputs?: { name: string }[] } } | null)?.manifest?.inputs ?? []);
  return inputs.some((i) => i.name === name);
}

/** Create the run blueprint when missing; a refusal (e.g. a plan limit) surfaces as the error text, never worked around. */
export async function ensureRunBlueprint(port: PortClient): Promise<"created" | "extended" | "current"> {
  return port.ensureBlueprintSchema(SKILL_RUN_BLUEPRINT as unknown as Parameters<PortClient["ensureBlueprintSchema"]>[0]);
}

/** Upsert the run entity. If Port refuses only because the triggering user is not a Port user, retry without that relation
 *  and say so — the run evidence must not be lost to an optional link. */
export async function recordRunInPort(port: PortClient, r: RunForPort): Promise<{ identifier: string; note?: string }> {
  await ensureRunBlueprint(port);
  const e = runEntity(r);
  try { await port.upsertEntity(RUN_BLUEPRINT_ID, e); return { identifier: e.identifier }; }
  catch (err) {
    if (!("triggered_by" in e.relations)) throw err;
    const bare = runEntity(r, { withUser: false });
    await port.upsertEntity(RUN_BLUEPRINT_ID, bare);
    return { identifier: bare.identifier, note: `triggered_by not set: ${(err as Error).message}` };
  }
}
