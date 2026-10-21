/* Server-side bridge to the Python runtime (api/py/run.py) and the one function every run goes through:
 * UI test runs, evaluation cases and consumer-API invocations all call executeRun(). Server only. */
import type { Manifest } from "./manifest";
import { checkPin } from "./pins";
import { validateOutputContract, type RunInput, type OutputFile } from "./schema";
import type { PolicyRow, VersionSource, RunStatus } from "./db";

export interface RuntimeResponse {
  run_id: string; status: "succeeded" | "failed" | "needs_input" | "timeout"; exit_code: number | null;
  run_json: Record<string, unknown> | null; needs_input: { missing: { name: string; type: string; question: string }[] } | null;
  outputs: OutputFile[]; logs: string;
  provider: { requested: string; used: string; available: boolean; note: string };
  model: string | null; usage: Record<string, unknown> | null;
  cost: { usd: number | null; is_estimate: boolean; basis: string | null };
  duration_ms: number; timed_out: boolean; case_checks: { check: string; pass: boolean; evidence: string }[] | null; error: string | null;
  runtime: { python: string; runtime_version: string; runner_version: string };
}

export interface RuntimeConfig { ok: boolean; url: string | null; reason: string | null }

/** Where the Python function lives and whether this server can call it. Checked, not assumed. */
export function runtimeConfig(): RuntimeConfig {
  const secret = process.env.SF_RUNTIME_SECRET;
  const explicit = process.env.SF_RUNTIME_URL;
  const prodHost = process.env.VERCEL_ENV === "production" ? process.env.VERCEL_PROJECT_PRODUCTION_URL : null;
  const host = explicit ?? (prodHost ? `https://${prodHost}` : process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : null);
  if (!secret) return { ok: false, url: host, reason: "SF_RUNTIME_SECRET is not set on the server (the Python runtime refuses calls without it)." };
  if (!host) return { ok: false, url: null, reason: "No runtime URL: set SF_RUNTIME_URL (e.g. http://localhost:3000 under `vercel dev`), or deploy to Vercel where VERCEL_URL is provided." };
  return { ok: true, url: `${host.replace(/\/$/, "")}/api/py/run`, reason: null };
}

export const runtimeHeadersForServer = (): Record<string, string> => runtimeHeaders();

function runtimeHeaders(): Record<string, string> {
  const h: Record<string, string> = { "content-type": "application/json", "x-sf-runtime-secret": process.env.SF_RUNTIME_SECRET ?? "" };
  // Vercel deployment protection (preview URLs): pass the bypass secret when the project has one
  if (process.env.VERCEL_AUTOMATION_BYPASS_SECRET) h["x-vercel-protection-bypass"] = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
  return h;
}

export async function runtimeHealth(): Promise<{ ok: boolean; detail: Record<string, unknown> | null; error: string | null; url: string | null }> {
  const cfg = runtimeConfig();
  if (!cfg.ok || !cfg.url) return { ok: false, detail: null, error: cfg.reason, url: cfg.url };
  try {
    const res = await fetch(cfg.url, { headers: runtimeHeaders(), cache: "no-store", signal: AbortSignal.timeout(15_000) });
    const body = await res.json().catch(() => null);
    if (!res.ok) return { ok: false, detail: body, error: `runtime responded HTTP ${res.status}${body?.error ? `: ${body.error}` : ""}`, url: cfg.url };
    return { ok: true, detail: body, error: null, url: cfg.url };
  } catch (e) {
    return { ok: false, detail: null, error: `runtime unreachable: ${(e as Error).message}`, url: cfg.url };
  }
}

/** POST one run request to the Python runtime. The single network path every run takes (skills, evals, API,
 *  scorecards). Never throws: transport and protocol failures come back as {ok:false, error}. */
export async function callRuntime(url: string, body: Record<string, unknown>, timeoutMs = 59_000): Promise<{ ok: true; r: RuntimeResponse } | { ok: false; error: string }> {
  try {
    const res = await fetch(url, { method: "POST", headers: runtimeHeaders(), body: JSON.stringify(body), cache: "no-store", signal: AbortSignal.timeout(timeoutMs) });
    const json = await res.json().catch(() => null);
    if (!res.ok || !json || typeof json !== "object" || !("status" in json)) return { ok: false, error: `runtime HTTP ${res.status}${json?.error ? `: ${json.error}` : ""}` };
    return { ok: true, r: json as RuntimeResponse };
  } catch (e) {
    return { ok: false, error: `runtime call failed: ${(e as Error).name === "TimeoutError" ? `the runtime did not answer within ${Math.round(timeoutMs / 1000)} s` : (e as Error).message}` };
  }
}

/** Path inputs always live under the run folder (outputs are collected from there; scripts never write elsewhere).
 *  An example folder given for one (an evaluation case's fixture) is copied there first, so the example is never written to.
 *  A case that checks the skill asks for a missing path input (needs_input:<name>) gets no default for it. */
export function pathInputs(manifest: Manifest, given: Record<string, RunInput>, checks?: unknown[]): Record<string, RunInput> {
  const inputs: Record<string, RunInput> = { ...given };
  const asked = new Set((checks ?? []).filter((c): c is string => typeof c === "string" && c.startsWith("needs_input:")).map((c) => c.slice("needs_input:".length).trim()));
  for (const spec of manifest.inputs) {
    if (spec.type !== "path") continue;
    const g = inputs[spec.name];
    if (g?.kind === "fixture") inputs[spec.name] = { kind: "fixture", path: g.path, into_out: true };
    else if (g?.kind === "value" && g.value.startsWith("{out}/")) continue;
    else if (!g && asked.has(spec.name)) delete inputs[spec.name];
    else inputs[spec.name] = { kind: "value", value: `{out}/${spec.name}` };
  }
  return inputs;
}

export interface ExecuteOptions {
  runId: string;
  manifest: Manifest;
  source: VersionSource;
  slug: string;
  files: { path: string; content: string }[];
  inputs: Record<string, RunInput>;
  assumptions: Record<string, string>;
  policy: PolicyRow | null;
  /** Evaluation-case checks to evaluate after the run (deterministic vocabulary from scripts/check_output.py). */
  checks?: unknown[];
  /** Re-read before execution: a run cancelled while queued never starts. */
  isCancelled?: () => Promise<boolean>;
  /** Version status; anything past draft must run on its pinned repository files. */
  status?: string;
  /** The version being run: a repo version past draft runs on its frozen files (lib/factory/snapshot.ts). */
  versionId?: string;
}

export interface RunPatch {
  status: RunStatus; run_json: Record<string, unknown> | null; outputs: OutputFile[]; logs: string; provider: string | null; model: string | null;
  usage: Record<string, unknown> | null; cost_usd: number | null; cost_is_estimate: boolean; started_at: string; finished_at: string; duration_ms: number; error: string | null;
}

/** Policy gate (tools, provider), runtime call, output-contract validation. Returns what to persist on sf_runs. */
export async function executeRun(o: ExecuteOptions): Promise<RunPatch & { response: RuntimeResponse | null }> {
  const started = new Date();
  const base = (status: RunStatus, error: string | null, extra: Partial<RunPatch> = {}): RunPatch & { response: RuntimeResponse | null } => ({
    status, run_json: null, outputs: [], logs: "", provider: null, model: null, usage: null, cost_usd: null, cost_is_estimate: true,
    started_at: started.toISOString(), finished_at: new Date().toISOString(), duration_ms: Date.now() - started.getTime(), error, response: null, ...extra,
  });

  if (o.isCancelled && (await o.isCancelled())) return base("cancelled", "cancelled before it started");

  // workspace policy: tools and providers are allowlists, enforced here (server) not in the UI
  const tools = new Set(o.manifest.run.map((s) => s.kind));
  const allowedTools = o.policy?.allowed_tools ?? ["script", "llm"];
  const blocked = [...tools].filter((t) => !allowedTools.includes(t));
  if (blocked.length) return base("failed", `workspace policy does not allow tool(s): ${blocked.join(", ")}`);
  const provider = o.manifest.model_config.provider;
  const allowedProviders = o.policy?.allowed_providers ?? ["none", "anthropic", "openai_compat"];
  if (!allowedProviders.includes(provider)) return base("failed", `workspace policy does not allow provider "${provider}"`);

  // a library version past draft runs on the files it was reviewed with (frozen copy), so library changes never stop it
  let frozen: { files: { path: string; content: string }[]; sha256: string } | null = null;
  if (o.source.kind === "repo" && o.versionId && o.status && o.status !== "draft") {
    try {
      const { ensureSnapshot } = await import("./snapshot");
      frozen = await ensureSnapshot(o.versionId);
    } catch (e) {
      return base("failed", `frozen files: ${(e as Error).message}`);
    }
  }
  const pin = frozen ? { ok: true as const, note: null } : checkPin(o.source, o.status);
  if (!pin.ok) return base("failed", pin.reason);

  const cfg = runtimeConfig();
  if (!cfg.ok || !cfg.url) return base("failed", `runtime not configured — ${cfg.reason}`);

  const inputs = pathInputs(o.manifest, o.inputs, o.checks);

  const body = {
    run_id: o.runId,
    skill: o.source.kind === "repo"
      ? { kind: "repo", repo_skill: o.source.repo_skill, ...(frozen ? { snapshot: frozen.files, snapshot_sha: frozen.sha256 } : {}) }
      : { kind: "authored", slug: o.slug, manifest: o.manifest, files: o.files },
    inputs, assumptions: o.assumptions,
    provider, model: o.manifest.model_config.model, temperature: o.manifest.model_config.temperature, max_tokens: o.manifest.model_config.max_tokens,
    timeout_s: o.manifest.limits.timeout_s, max_retries: o.manifest.limits.max_retries, checks: o.checks ?? null,
  };

  const called = await callRuntime(cfg.url, body);
  if (!called.ok) return base("failed", called.error);
  const r = called.r;

  // output contract: a run that "succeeded" but did not produce every declared output (or produced invalid JSON) is a failure
  let status: RunStatus = r.status;
  let error = r.error;
  const outDir = typeof r.run_json?.out === "string" ? (r.run_json.out as string) : null;
  const resolveInput = (name: string) => {
    const v = (r.run_json?.inputs as Record<string, string> | undefined)?.[name];
    if (!outDir || typeof v !== "string") return null;
    if (v === outDir) return "";
    return v.startsWith(outDir + "/") ? v.slice(outDir.length + 1) : null;
  };
  const contract = validateOutputContract(o.manifest, r.outputs, resolveInput);
  if (status === "succeeded" && !contract.ok) {
    status = "failed";
    error = `output contract: ${contract.problems.map((p) => `${p.path} ${p.message}`).join("; ")}`;
  }
  const runJson = { ...(r.run_json ?? {}), factory: { contract, provider: r.provider, case_checks: r.case_checks, runtime: r.runtime, needs_input: r.needs_input, exit_code: r.exit_code } };
  return {
    status, run_json: runJson, outputs: r.outputs, logs: (pin.note ? `[factory] ${pin.note}\n` : "") + r.logs,
    provider: r.provider.used, model: r.model, usage: r.usage, cost_usd: r.cost.usd, cost_is_estimate: r.cost.is_estimate,
    started_at: started.toISOString(), finished_at: new Date().toISOString(), duration_ms: r.duration_ms || Date.now() - started.getTime(),
    error, response: r,
  };
}
