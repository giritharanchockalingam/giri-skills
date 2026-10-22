/* Executor dispatch: hands a queued delivery run to where code can run. Server only (reads env).
 *   github-actions — `workflow_dispatch` of delivery.yml in the giri-skills repository (DELIVERY_GITHUB_TOKEN).
 *   ide / local    — records only: the developer runs scripts/deliver.py and posts evidence back.
 * Without a token the run stays queued with a notice; nothing is pretended. */
import type { DeliveryRun } from "./core";
import { deliverCommand, NO_EXECUTOR_NOTICE } from "./core";

export interface DispatchResult { ok: boolean; executor_ref: string; notice?: string }
export interface GithubDispatchEnv { token?: string; repo?: string; ref?: string; fetch?: typeof fetch }

export const DELIVERY_ENV = {
  token: "DELIVERY_GITHUB_TOKEN",   // fine-grained PAT or GitHub App token with `actions: write` on the library repo
  repo: "DELIVERY_GITHUB_REPO",     // owner/name of the repository that holds .github/workflows/delivery.yml (default: giritharanchockalingam/giri-skills)
  ref: "DELIVERY_GITHUB_REF",       // branch of that repository to run the workflow from (default: main)
} as const;
export const DEFAULT_LIBRARY_REPO = "giritharanchockalingam/giri-skills";

/** Inputs delivery.yml receives (workflow_dispatch inputs are strings, max 10). */
export function workflowInputs(run: Pick<DeliveryRun, "id" | "pipeline" | "repo" | "ref" | "request" | "mode">, callbackUrl: string): Record<string, string> {
  return { run_id: run.id, pipeline: run.pipeline, mode: run.mode, repo: run.repo, ref: run.ref ?? "", request: run.request.slice(0, 8000), callback: callbackUrl };
}

export async function dispatchGithubActions(run: DeliveryRun, callbackUrl: string, env: GithubDispatchEnv = {}): Promise<DispatchResult> {
  const token = env.token ?? process.env[DELIVERY_ENV.token];
  const repo = env.repo ?? process.env[DELIVERY_ENV.repo] ?? DEFAULT_LIBRARY_REPO;
  const ref = env.ref ?? process.env[DELIVERY_ENV.ref] ?? "main";
  if (!token) return { ok: false, executor_ref: "", notice: NO_EXECUTOR_NOTICE };
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) return { ok: false, executor_ref: "", notice: `${DELIVERY_ENV.repo} must be owner/name (got ${JSON.stringify(repo)})` };
  const f = env.fetch ?? fetch;
  const url = `https://api.github.com/repos/${repo}/actions/workflows/delivery.yml/dispatches`;
  const res = await f(url, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, accept: "application/vnd.github+json", "x-github-api-version": "2022-11-28", "content-type": "application/json" },
    body: JSON.stringify({ ref, inputs: workflowInputs(run, callbackUrl) }),
  });
  if (res.status === 204) return { ok: true, executor_ref: `https://github.com/${repo}/actions/workflows/delivery.yml` };
  const text = await res.text().catch(() => "");
  return { ok: false, executor_ref: "", notice: `GitHub refused the dispatch (HTTP ${res.status})${text ? `: ${text.slice(0, 300)}` : ""}` };
}

/** Dispatch by the run's executor. `ide` and `local` only record the command the developer runs. */
export async function dispatch(run: DeliveryRun, opts: { callbackUrl: string; portalUrl: string; env?: GithubDispatchEnv }): Promise<DispatchResult> {
  if (run.executor === "github-actions") return dispatchGithubActions(run, opts.callbackUrl, opts.env);
  return { ok: true, executor_ref: run.executor, notice: `run locally: ${deliverCommand(run, opts.portalUrl)}` };
}
