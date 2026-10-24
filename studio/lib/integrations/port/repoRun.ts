/* WP4 — the server side of "run a governed skill on a PR" and of the run evidence (spec §4.3, §5.3, §7 steps 2–3).
 *  - resolveRepoRun: Port repository entity → GitHub owner/repo (from the entity's url) → the factory's GitHub App
 *    installation for that repo (catalog) → the PR's diff, head commit and URL. The diff becomes the skill's `diff` input
 *    only when the published skill declares one; nothing else is guessed.
 *  - recordRunInPort: one `sf_skill_run` entity per Port-started factory run, related to the skill, the repository and
 *    (when Port knows the e-mail as a user) who triggered it. Deterministic identifier (run_<factory run id>), so a
 *    retry upserts the same entity. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { PortClient } from "./client";
import { REPOSITORY_BLUEPRINT_ID, RUN_BLUEPRINT_ID, SKILL_RUN_BLUEPRINT, PR_BLUEPRINT_ID, PR_REVIEW_AGGREGATION, PR_REVIEW_GATE_SCORECARD, REVIEW_SKILL, prEntityId, runEntity, type RunForPort } from "./map";
import { ensureScorecard } from "./scorecard";
import { githubConfig, installationToken, gh, createCheckRun, completeCheckRun } from "@/lib/github/app";

const MAX_DIFF_BYTES = 900_000;   // stays under Port's / the factory's 1 MiB body caps with room for the envelope

export interface RepoRunContext { fullName: string; pr: number; headSha: string; prUrl: string; title: string; diff: string; installationId: number }
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
    return { ok: true, ctx: { fullName, pr, headSha: meta.data.head.sha, prUrl: meta.data.html_url, title: meta.data.title, diff, installationId } };
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

/** Create/extend the run blueprint, the PR aggregation and the PR review gate. A refusal (e.g. a plan limit) surfaces as the
 *  error text, never worked around. */
export async function ensureRunBlueprint(port: PortClient): Promise<"created" | "extended" | "current"> {
  const r = await port.ensureBlueprintSchema(SKILL_RUN_BLUEPRINT as unknown as Parameters<PortClient["ensureBlueprintSchema"]>[0]);
  if (await port.getBlueprint(PR_BLUEPRINT_ID)) {
    await port.ensureAggregations(PR_BLUEPRINT_ID, PR_REVIEW_AGGREGATION);
    await ensureScorecard(port, PR_BLUEPRINT_ID, PR_REVIEW_GATE_SCORECARD);
  }
  return r;
}

/** Port workflows do not render the trigger user's e-mail into the body; the workflow run's createdBy (a user id) does
 *  resolve through Port's users list. Returns null when it cannot be resolved — never a guess. */
export async function resolveTriggerEmail(port: PortClient, portRunId: string): Promise<string | null> {
  try {
    const run = await port.getWorkflowRun(portRunId);
    const id = typeof run?.createdBy === "string" ? run.createdBy : null;
    if (!id) return null;
    return (await port.listUsers()).find((u) => u.id === id)?.email ?? null;
  } catch { return null; }
}

/** Upsert the run entity. Optional links (user, PR) that Port refuses are dropped one at a time and named in the note —
 *  the run evidence itself is never lost to an optional link. */
export async function recordRunInPort(port: PortClient, r: RunForPort): Promise<{ identifier: string; note?: string }> {
  await ensureRunBlueprint(port);
  const attempts: { opts: Parameters<typeof runEntity>[1]; label: string }[] = [
    { opts: { withUser: true, withPr: true }, label: "" },
    { opts: { withUser: false, withPr: true }, label: "triggered_by not set" },
    { opts: { withUser: false, withPr: false }, label: "triggered_by and pull_request not set" },
  ];
  let lastErr: unknown = null;
  for (const a of attempts) {
    const e = runEntity(r, a.opts);
    try {
      await port.upsertEntity(RUN_BLUEPRINT_ID, e);
      if (r.repository && r.pr && r.headSha) await supersedeHeadReviews(port, r.repository, r.pr, r.headSha);
      return { identifier: e.identifier, ...(a.label ? { note: `${a.label}: ${(lastErr as Error).message}` } : {}) };
    } catch (err) { lastErr = err; }
  }
  throw lastErr;
}

/** A PR moved to `headSha`: every earlier run on that PR that still claims to be on the head is marked off it, so the
 *  PR's "Passing reviews on head" counts only reviews of the current commit. Returns how many runs were updated. */
export async function supersedeHeadReviews(port: PortClient, repository: string, pr: number, headSha: string): Promise<number> {
  const stale = await port.searchEntities(RUN_BLUEPRINT_ID, { combinator: "and", rules: [
    { property: "sf_pr_number", operator: "=", value: pr },
    { property: "sf_is_head_review", operator: "=", value: true },
    { property: "sf_head_sha", operator: "!=", value: headSha },
  ] });
  // the repository is matched here rather than in the query: a PR number is only unique within its repository
  for (const e of stale.filter((x) => (x.relations as Record<string, unknown> | undefined)?.target === repository)) await port.upsertEntity(RUN_BLUEPRINT_ID, { identifier: String(e.identifier), properties: { sf_is_head_review: false } } as { identifier: string });
  return stale.filter((x) => (x.relations as Record<string, unknown> | undefined)?.target === repository).length;
}

/** §7 step 4: the result on the PR itself — a GitHub check run on the reviewed commit, linking the factory run and Port. */
export async function postReviewCheck(ctx: RepoRunContext, r: { slug: string; version: number | null; status: string; checksPassed: number; checksTotal: number; factoryUrl: string; portRunEntity: string; portAppUrl: string }, f?: typeof fetch): Promise<{ url: string } | null> {
  const c = githubConfig();
  if (!c.ok) return null;
  const token = await installationToken(c.cfg, ctx.installationId, f);
  const name = `Skills Factory: ${r.slug}`.slice(0, 100);
  const check = await createCheckRun(token, ctx.fullName, { name, head_sha: ctx.headSha, details_url: r.factoryUrl, external_id: r.portRunEntity }, f);
  const ok = r.status === "succeeded";
  await completeCheckRun(token, ctx.fullName, check.id, {
    conclusion: ok ? "success" : "failure",
    title: `${r.slug} v${r.version ?? "?"} — ${r.status} (${r.checksPassed}/${r.checksTotal} checks)`,
    summary: [`Factory run: ${r.factoryUrl}`, `Port run entity: ${r.portAppUrl.replace(/\/$/, "")}/${RUN_BLUEPRINT_ID}Entity?identifier=${encodeURIComponent(r.portRunEntity)}`,
      r.slug === REVIEW_SKILL ? (ok ? "This commit is reviewed for the Port PR review gate." : "The Port PR review gate stays closed for this commit.") : ""].filter(Boolean).join("\n\n"),
    details_url: r.factoryUrl,
  }, f);
  return { url: check.html_url };
}

export { prEntityId };
