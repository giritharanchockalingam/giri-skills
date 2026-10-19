/* Sync a workspace's GitHub installations into the catalog (sf_catalog_entities). Server only.
 * Runs as the signed-in author/admin (RLS applies); reads GitHub with short-lived installation tokens.
 * Idempotent: entities are upserted by (workspace, kind, key); repos no longer visible are marked archived with the
 * reason, never silently deleted. Every sync is logged in sf_catalog_syncs with counts or the error. */
import { refreshDelivery } from "@/lib/insights/deliveryRefresh";
import type { SupabaseClient } from "@supabase/supabase-js";
import { githubConfig, installationToken, listInstallationRepos, repoPaths, fileText, type GhRepo, type GithubConfig } from "./app.ts";
import { detect, defaultOwner, CODEOWNERS_PATHS } from "./detect.ts";

export const MAX_REPOS_PER_SYNC = 300;
const CONCURRENCY = 6;

async function pool<T, R>(items: T[], n: number, fn: (t: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) { const k = i++; out[k] = await fn(items[k]); }
  }));
  return out;
}

export interface RepoProfile {
  key: string; external_id: string; title: string; url: string; owner: string | null; archived: boolean; last_activity_at: string | null;
  properties: Record<string, unknown>;
}

/** Everything the catalog knows about one repository, from GitHub (tree + root manifests + CODEOWNERS). */
export async function profileRepo(token: string, repo: GhRepo, fetchImpl?: typeof fetch): Promise<RepoProfile> {
  const { paths, truncated } = await repoPaths(token, repo, fetchImpl);
  const want = (p: string) => (paths.includes(p) ? fileText(token, repo.full_name, p, fetchImpl) : Promise.resolve(null));
  const coPath = CODEOWNERS_PATHS.find((p) => paths.includes(p)) ?? null;
  const [packageJson, requirements, pyproject, codeowners] = await Promise.all([want("package.json"), want("requirements.txt"), want("pyproject.toml"), coPath ? want(coPath) : Promise.resolve(null)]);
  const d = detect(paths, { packageJson, requirements, pyproject });
  return {
    key: repo.full_name, external_id: String(repo.id), title: repo.name, url: repo.html_url,
    owner: defaultOwner(codeowners), archived: repo.archived, last_activity_at: repo.pushed_at,
    properties: {
      description: repo.description, visibility: repo.private ? "private" : "public", fork: repo.fork, default_branch: repo.default_branch,
      language: repo.language, topics: repo.topics ?? [], stack: d.stack, applicable: d.applicable, counts: d.counts,
      tree_truncated: truncated, owner_source: coPath,
    },
  };
}

export interface SyncResult { ok: boolean; message: string; repos: number; archived: number; errors: string[] }

export async function syncWorkspace(sb: SupabaseClient, workspaceId: string, userId: string, cfgIn?: GithubConfig): Promise<SyncResult> {
  const c = cfgIn ? { ok: true as const, cfg: cfgIn } : githubConfig();
  if (!c.ok) return { ok: false, message: `GitHub App not configured (missing ${c.missing.join(", ")})`, repos: 0, archived: 0, errors: [] };
  const { data: insts, error } = await sb.from("sf_github_installations").select("installation_id, account_login, suspended_at").eq("workspace_id", workspaceId);
  if (error) return { ok: false, message: error.message, repos: 0, archived: 0, errors: [] };
  if (!insts?.length) return { ok: false, message: "No GitHub installation linked to this workspace yet.", repos: 0, archived: 0, errors: [] };

  let total = 0, archivedN = 0;
  const errors: string[] = [];
  for (const inst of insts) {
    if (inst.suspended_at) { errors.push(`${inst.account_login}: installation suspended on GitHub`); continue; }
    const { data: log } = await sb.from("sf_catalog_syncs").insert({ workspace_id: workspaceId, installation_id: inst.installation_id, started_by: userId }).select("id").single();
    const finish = (patch: Record<string, unknown>) => log ? sb.from("sf_catalog_syncs").update({ ...patch, finished_at: new Date().toISOString() }).eq("id", log.id) : Promise.resolve();
    try {
      const token = await installationToken(c.cfg, inst.installation_id);
      const { items, truncated } = await listInstallationRepos(token);
      const repos = items.slice(0, MAX_REPOS_PER_SYNC);
      const repoErrors: string[] = [];
      const profiles = (await pool(repos, CONCURRENCY, async (r) => {
        try { return await profileRepo(token, r); } catch (e) { repoErrors.push(`${r.full_name}: ${(e as Error).message}`); return null; }
      })).filter((p): p is RepoProfile => !!p);
      const now = new Date().toISOString();
      if (profiles.length) {
        const { error: ue } = await sb.from("sf_catalog_entities").upsert(
          profiles.map((p) => ({ workspace_id: workspaceId, kind: "repository", source: "github", installation_id: inst.installation_id, synced_at: now, ...p })),
          { onConflict: "workspace_id,kind,key" });
        if (ue) throw new Error(ue.message);
      }
      // repos this installation no longer exposes: keep the record, mark it archived with the reason
      const seen = new Set(profiles.map((p) => p.key));
      const { data: existing } = await sb.from("sf_catalog_entities").select("id, key, properties").eq("workspace_id", workspaceId).eq("installation_id", inst.installation_id).eq("archived", false);
      const gone = (existing ?? []).filter((e) => !seen.has(e.key) && !repoErrors.some((m) => m.startsWith(`${e.key}:`)));
      for (const g of gone) {
        await sb.from("sf_catalog_entities").update({ archived: true, properties: { ...(g.properties as object), access_removed_at: now } }).eq("id", g.id);
      }
      total += profiles.length; archivedN += gone.length;
      errors.push(...repoErrors);
      if (truncated || items.length > MAX_REPOS_PER_SYNC) errors.push(`${inst.account_login}: more than ${Math.min(items.length, MAX_REPOS_PER_SYNC)} repositories — first ${MAX_REPOS_PER_SYNC} synced`);
      await finish({ status: "succeeded", counts: { repos: profiles.length, archived: gone.length, failed: repoErrors.length } });
    } catch (e) {
      const msg = (e as Error).message;
      errors.push(`${inst.account_login}: ${msg}`);
      await finish({ status: "failed", error: msg.slice(0, 1000) });
    }
  }
  // delivery metrics ride along with the sync; a failure here is reported, never fatal to the catalog
  if (total > 0) {
    try { const d = await refreshDelivery(sb, workspaceId, userId); errors.push(...d.errors.map((m) => `delivery metrics — ${m}`)); }
    catch (e) { errors.push(`delivery metrics: ${(e as Error).message}`); }
  }
  return { ok: errors.length === 0 || total > 0, message: `${total} repositor${total === 1 ? "y" : "ies"} synced${archivedN ? `, ${archivedN} no longer visible` : ""}${errors.length ? `; ${errors.length} problem(s)` : ""}.`, repos: total, archived: archivedN, errors };
}
