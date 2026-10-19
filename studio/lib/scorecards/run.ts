/* Score one catalog entity: fetch the files each applicable check needs from GitHub (installation token, the
 * default branch's current commit), run the library skill on the Python runtime, record the verdict as evidence.
 * Server only. Runs as the signed-in author/admin (RLS). One entity per call keeps each request inside the
 * function's time limit; the UI calls it repository by repository and shows progress. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { githubConfig, installationToken, repoTree, blobText, headSha, type GhRepo } from "@/lib/github/app";
import { callRuntime, runtimeConfig } from "@/lib/factory/runtime";
import { checksFor, bound, type CheckDef, type Scored, type TreeFile } from "./checks";

const FETCH_CONCURRENCY = 8;
const REPORT_EXCERPT = 60_000;

async function pool<T, R>(items: T[], n: number, fn: (t: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => { while (i < items.length) { const k = i++; out[k] = await fn(items[k]); } }));
  return out;
}

export interface CheckResult { check: string; title: string; verdict: Scored["verdict"]; summary: string }
export interface EntityScore { ok: boolean; entity: string; message: string; results: CheckResult[] }

type EntityRow = { id: string; key: string; installation_id: number | null; properties: { default_branch?: string; stack?: { id: string }[]; counts?: { migrations: number; files: number } } };

export async function scoreEntity(sb: SupabaseClient, workspaceId: string, userId: string, entityId: string): Promise<EntityScore> {
  const c = githubConfig();
  if (!c.ok) return { ok: false, entity: entityId, message: "GitHub App not configured.", results: [] };
  const rt = runtimeConfig();
  if (!rt.ok || !rt.url) return { ok: false, entity: entityId, message: `Runtime not available: ${rt.reason}`, results: [] };
  const { data: e } = await sb.from("sf_catalog_entities").select("id, key, installation_id, properties").eq("workspace_id", workspaceId).eq("id", entityId).maybeSingle<EntityRow>();
  if (!e) return { ok: false, entity: entityId, message: "Not in this workspace's catalog.", results: [] };
  if (!e.installation_id) return { ok: false, entity: e.key, message: "No GitHub installation for this repository any more.", results: [] };
  const checks = checksFor({ stackIds: (e.properties.stack ?? []).map((s) => s.id), counts: e.properties.counts ?? { migrations: 0, files: 0 } });
  if (!checks.length) return { ok: true, entity: e.key, message: "No scorecard checks apply to this repository yet.", results: [] };

  const token = await installationToken(c.cfg, e.installation_id);
  const repo = { full_name: e.key, default_branch: e.properties.default_branch ?? "main" } as GhRepo;
  const [tree, sha] = await Promise.all([repoTree(token, repo), headSha(token, repo)]);
  const blobCache = new Map<string, Promise<string | null>>();
  const text = (f: TreeFile) => { if (!blobCache.has(f.sha)) blobCache.set(f.sha, blobText(token, e.key, f.sha)); return blobCache.get(f.sha)!; };

  const results: CheckResult[] = [];
  for (const chk of checks) results.push(await runCheck(sb, workspaceId, userId, e, chk, tree.files, tree.truncated, sha, text, rt.url));
  const bad = results.filter((r) => r.verdict === "fail" || r.verdict === "error").length;
  return { ok: true, entity: e.key, message: `${results.length} check(s): ${results.length - bad} without failures`, results };
}

async function runCheck(sb: SupabaseClient, workspaceId: string, userId: string, e: EntityRow, chk: CheckDef, tree: TreeFile[], truncated: boolean,
  sha: string | null, text: (f: TreeFile) => Promise<string | null>, url: string): Promise<CheckResult> {
  const t0 = Date.now();
  const inputs: Record<string, unknown> = {};
  let partial = truncated, used = 0;
  for (const sel of chk.select(tree)) {
    const b = bound(sel.files);
    partial ||= b.partial;
    const contents = await pool(b.files, FETCH_CONCURRENCY, async (f) => ({ f, t: await text(f) }));
    const files = contents.filter((x) => x.t !== null).map((x) => ({ path: sel.strip ? x.f.path.slice(sel.strip.length + 1) : x.f.path, content: x.t as string }));
    used += files.length;
    if (files.length) inputs[sel.input] = { kind: "files", files };
  }
  for (const [k, v] of Object.entries(chk.values ?? {})) inputs[k] = { kind: "value", value: v };
  if (chk.id === "observability") inputs.target = { kind: "value", value: "{out}/target" };   // dry run inside the run folder

  let scored: Scored, details: Record<string, unknown>;
  if (!Object.values(inputs).some((v) => (v as { kind: string }).kind === "files") && chk.id !== "observability") {
    scored = { verdict: "skipped", summary: "no matching files in the repository", findings: null };
    details = { files_used: 0 };
  } else {
    const called = await callRuntime(url, { run_id: crypto.randomUUID(), skill: { kind: "repo", repo_skill: chk.skill }, inputs, assumptions: {}, provider: "none", model: null, timeout_s: 50, max_retries: 0 });
    if (!called.ok) {
      scored = { verdict: "error", summary: called.error, findings: null };
      details = { files_used: used };
    } else {
      const r = called.r;
      const outs = r.outputs.map((o) => ({ path: o.path, content_text: o.content_text }));
      scored = r.status === "needs_input" ? { verdict: "error", summary: `the skill needs input: ${(r.needs_input?.missing ?? []).map((m) => m.name).join(", ")}`, findings: null } : chk.score(outs, r.status);
      details = {
        files_used: used, partial, runtime_status: r.status, exit_code: r.exit_code, error: r.error,
        report: (outs.find((o) => o.path === chk.primary)?.content_text ?? "").replace(/\/tmp\/sf\/[^\s/]+\/(inputs|out)\/?/g, "").slice(0, REPORT_EXCERPT),
        outputs: r.outputs.map((o) => ({ path: o.path, bytes: o.bytes, sha256: o.sha256 })), runtime: r.runtime,
      };
    }
  }
  if (partial) scored = { ...scored, summary: `${scored.summary} (partial: repository larger than the scan limit)` };
  await sb.from("sf_scorecard_results").insert({
    workspace_id: workspaceId, entity_id: e.id, check_id: chk.id, skill: chk.skill, verdict: scored.verdict, summary: scored.summary.slice(0, 500),
    findings: scored.findings, commit_sha: sha, details, duration_ms: Date.now() - t0, run_by: userId,
  });
  return { check: chk.id, title: chk.title, verdict: scored.verdict, summary: scored.summary };
}
