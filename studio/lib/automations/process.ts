/* Workflow orchestrator — the I/O: act on one verified, de-duplicated GitHub event. Server only.
 *   repos_changed → re-sync the installation's repositories into the catalog (the Context Lake stays live)
 *   push (default branch) → re-profile the repository; matching automations score it (it IS the scorecard)
 *   pull_request → matching automations score the PR's head commit and report a Check Run on the PR
 * Runs with the service-role client (no user session); every query is scoped to the workspace that owns the
 * installation. Each automation run is recorded with its verdicts, the commit, and the GitHub link. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { createAdminSupabase } from "@/lib/supabase/server-admin";
import { githubConfig, installationToken, getRepo, createCheckRun, completeCheckRun, type GithubConfig } from "@/lib/github/app";
import { profileRepo, syncWorkspace } from "@/lib/github/sync";
import { scoreEntity } from "@/lib/scorecards/run";
import { log } from "@/lib/logger";
import { matchAutomations, unionChecks, checkRunOutput, type NormEvent, type AutomationRow } from "./webhook";

export const CHECK_NAME_PREFIX = "Skills Factory";

/** Everything processEvent touches outside itself — injected so every path is testable without GitHub or a runtime. */
export interface ProcessDeps {
  sb: SupabaseClient;
  config: () => ReturnType<typeof githubConfig>;
  installationToken: (cfg: GithubConfig, installationId: number) => Promise<string>;
  getRepo: typeof getRepo;
  profileRepo: typeof profileRepo;
  syncWorkspace: typeof syncWorkspace;
  scoreEntity: typeof scoreEntity;
  createCheckRun: typeof createCheckRun;
  completeCheckRun: typeof completeCheckRun;
}
export const defaultDeps = (sb?: SupabaseClient): ProcessDeps => ({
  sb: sb ?? createAdminSupabase(), config: githubConfig, installationToken, getRepo, profileRepo, syncWorkspace, scoreEntity, createCheckRun, completeCheckRun,
});

export async function processEvent(e: NormEvent, deliveryId: string, origin: string, deps: ProcessDeps = defaultDeps()): Promise<{ handled: string }> {
  const { sb } = deps;
  const c = deps.config();
  if (!c.ok) return { handled: "github app not configured" };
  const { data: inst } = await sb.from("sf_github_installations").select("workspace_id, installation_id, verified_by, suspended_at").eq("installation_id", e.installationId).maybeSingle();
  if (!inst || inst.suspended_at) return { handled: "installation not linked to a workspace" };
  const ws = inst.workspace_id as string;

  if (e.kind === "repos_changed") {
    const r = await deps.syncWorkspace(sb, ws, inst.verified_by as string, c.cfg);
    return { handled: `catalog re-synced: ${r.message}` };
  }

  const token = await deps.installationToken(c.cfg, e.installationId);
  // keep the Context Lake current: a push to the default branch re-profiles the repository (or adds it)
  let { data: entity } = await sb.from("sf_catalog_entities").select("id, key").eq("workspace_id", ws).eq("kind", "repository").eq("key", e.repo).maybeSingle();
  if (e.kind === "push" || !entity) {
    const p = await deps.profileRepo(token, await deps.getRepo(token, e.repo));
    const { data: up } = await sb.from("sf_catalog_entities").upsert(
      { workspace_id: ws, kind: "repository", source: "github", installation_id: e.installationId, synced_at: new Date().toISOString(), ...p },
      { onConflict: "workspace_id,kind,key" }).select("id, key").single();
    entity = up ?? entity;
  }
  if (!entity) return { handled: "repository not in catalog" };

  const { data: autosRaw } = await sb.from("sf_automations").select("id, name, trigger, repos, checks, report_to_github, enabled, created_by").eq("workspace_id", ws).eq("enabled", true);
  const autos = matchAutomations(e, (autosRaw ?? []) as AutomationRow[]);
  if (!autos.length) return { handled: e.kind === "push" ? "repository re-profiled; no automation" : "no automation matched" };

  const pr = e.kind === "pull_request" ? e.pr : null;
  const detailsUrl = `${origin}/catalog/${entity.id}`;
  const runs: { a: AutomationRow; runId: string; checkRun: { id: number; html_url: string } | null }[] = [];
  for (const a of autos) {
    let checkRun: { id: number; html_url: string } | null = null;
    if (a.report_to_github) {
      try { checkRun = await deps.createCheckRun(token, e.repo, { name: `${CHECK_NAME_PREFIX}: ${a.name}`.slice(0, 100), head_sha: e.sha, details_url: detailsUrl, external_id: a.id }); }
      catch (err) { log.warn({ action: "automation.check_run.create", repo: e.repo, err }, "could not create check run (missing checks: write?)"); }
    }
    const { data: run } = await sb.from("sf_automation_runs").insert({ workspace_id: ws, automation_id: a.id, entity_id: entity.id, repo: e.repo, event: e.kind,
      delivery_id: deliveryId, head_sha: e.sha, pr_number: pr, check_run_url: checkRun?.html_url ?? null }).select("id").single();
    if (!run) {
      log.error({ action: "automation.run.insert", repo: e.repo }, "could not record the automation run");
      if (checkRun) await deps.completeCheckRun(token, e.repo, checkRun.id, { conclusion: "neutral", title: "Could not run the scorecard",
        summary: "The run could not be recorded. This is a problem on the Skills Factory side, not a verdict on this code.", details_url: detailsUrl }).catch(() => undefined);
      continue;
    }
    runs.push({ a, runId: run.id as string, checkRun });
  }

  if (!runs.length) return { handled: "could not record any automation run" };
  // one scorecard run for all matching automations (union of their checks), attributed to the first automation's run
  let score: Awaited<ReturnType<typeof scoreEntity>> | null = null, failure: string | null = null;
  try {
    score = await deps.scoreEntity(sb, ws, runs[0].a.created_by, entity.id, { ref: e.sha, context: e.kind === "pull_request" ? "pull_request" : "default", prNumber: pr, baseSha: e.kind === "pull_request" ? e.baseSha ?? undefined : undefined, checks: unionChecks(runs.map((r) => r.a)), automationRunId: runs[0].runId });
    if (!score.ok) failure = score.message;
  } catch (err) { failure = (err as Error).message; log.error({ action: "automation.score", repo: e.repo, err }, "scorecard run failed"); }

  for (const { a, runId, checkRun } of runs) {
    const mine = (score?.results ?? []).filter((r) => !a.checks.length || a.checks.includes(r.check));
    const out = failure ? { conclusion: "neutral" as const, title: "Could not run the scorecard", summary: `The checks did not run: ${failure}\n\nThis is a problem on the Skills Factory side, not a verdict on this code.` }
      : checkRunOutput(mine, detailsUrl, e.kind === "pull_request" ? `Scored the head commit of #${e.pr} (\`${e.sha.slice(0, 7)}\`)${e.baseSha ? ` against its base (\`${e.baseSha.slice(0, 7)}\`): findings checks fail only on what this PR adds` : ""}.` : `Scored \`${e.sha.slice(0, 7)}\` on the default branch.`);
    await sb.from("sf_automation_runs").update({ status: failure ? "failed" : "succeeded", error: failure, finished_at: new Date().toISOString(),
      verdicts: Object.fromEntries(mine.map((r) => [r.check, { verdict: r.verdict, summary: r.summary }])) }).eq("id", runId);
    if (checkRun) {
      try { await deps.completeCheckRun(token, e.repo, checkRun.id, { ...out, details_url: detailsUrl }); }
      catch (err) { log.warn({ action: "automation.check_run.complete", repo: e.repo, err }, "could not complete check run"); }
    }
  }
  return { handled: `${autos.length} automation(s) ran on ${e.repo}@${e.sha.slice(0, 7)}${failure ? ` (failed: ${failure})` : ""}` };
}
