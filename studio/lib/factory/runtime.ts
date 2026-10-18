/* Server-side bridge to the Python runtime (api/py/run.py) and the one function every run goes through:
 * UI test runs, evaluation cases and consumer-API invocations all call executeRun(). Server only. */
import type { Manifest } from "./manifest";
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

  const cfg = runtimeConfig();
  if (!cfg.ok || !cfg.url) return base("failed", `runtime not configured — ${cfg.reason}`);

  // path inputs always live under the run folder (outputs are collected from there; scripts never write elsewhere)
  const inputs: Record<string, RunInput> = { ...o.inputs };
  for (const spec of o.manifest.inputs) {
    if (spec.type === "path") {
      const given = inputs[spec.name];
      inputs[spec.name] = { kind: "value", value: given?.kind === "value" && given.value.startsWith("{out}/") ? given.value : `{out}/${spec.name}` };
    }
  }

  const body = {
    run_id: o.runId,
    skill: o.source.kind === "repo" ? { kind: "repo", repo_skill: o.source.repo_skill } : { kind: "authored", slug: o.slug, manifest: o.manifest, files: o.files },
    inputs, assumptions: o.assumptions,
    provider, model: o.manifest.model_config.model, temperature: o.manifest.model_config.temperature, max_tokens: o.manifest.model_config.max_tokens,
    timeout_s: o.manifest.limits.timeout_s, max_retries: o.manifest.limits.max_retries, checks: o.checks ?? null,
  };

  let r: RuntimeResponse;
  try {
    const res = await fetch(cfg.url, { method: "POST", headers: runtimeHeaders(), body: JSON.stringify(body), cache: "no-store", signal: AbortSignal.timeout(59_000) });
    const json = await res.json().catch(() => null);
    if (!res.ok || !json || typeof json !== "object" || !("status" in json)) {
      return base("failed", `runtime HTTP ${res.status}${json?.error ? `: ${json.error}` : ""}`);
    }
    r = json as RuntimeResponse;
  } catch (e) {
    const msg = (e as Error).name === "TimeoutError" ? "the runtime did not answer within 59 s" : (e as Error).message;
    return base("failed", `runtime call failed: ${msg}`);
  }

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
    status, run_json: runJson, outputs: r.outputs, logs: r.logs,
    provider: r.provider.used, model: r.model, usage: r.usage, cost_usd: r.cost.usd, cost_is_estimate: r.cost.is_estimate,
    started_at: started.toISOString(), finished_at: new Date().toISOString(), duration_ms: r.duration_ms || Date.now() - started.getTime(),
    error, response: r,
  };
}
