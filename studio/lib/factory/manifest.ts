/* The skill manifest: the versioned contract every sf_skill_versions row stores as `manifest` (jsonb).
 *
 * Pure module (no Node/Next imports) so it runs in the browser (editor), on the server (route handlers)
 * and under `node --experimental-strip-types --test`. Hashing lives in hash.ts (node:crypto).
 *
 * Format (documented in docs/API.md → "Manifest format"):
 *   inputs / run / outputs use the same shape as the repo's SKILL.md `metadata.agent` block, which is what
 *   scripts/run_skill.py executes — so a manifest imported from the repo runs unchanged, and an authored
 *   manifest is rendered back into a SKILL.md by the runtime. Secrets never appear here: `connections` names
 *   a workspace connection whose secret is an environment variable on the server.
 */

export type InputType = "csv" | "json" | "md" | "txt" | "file" | "sql" | "dir" | "path" | "string" | "args" | "flag";
export const INPUT_TYPES: readonly InputType[] = ["csv", "json", "md", "txt", "file", "sql", "dir", "path", "string", "args", "flag"];
/** Input types whose value is file content (the runtime writes it to a file before the run). */
export const TEXT_INPUT_TYPES: readonly InputType[] = ["csv", "json", "md", "txt", "file", "sql"];

export interface JsonSchema {
  type?: "object" | "array" | "string" | "number" | "integer" | "boolean" | "null";
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  enum?: (string | number | boolean | null)[];
  minimum?: number; maximum?: number;
  minLength?: number; maxLength?: number;
  pattern?: string;
  additionalProperties?: boolean;
  description?: string;
}

export interface InputSpec {
  name: string;
  type: InputType;
  required: boolean;
  /** Plain-language description of where the value comes from. */
  from: string;
  default: string | null;
  /** For `flag` inputs: the CLI flag emitted when truthy. */
  flag: string | null;
  /** Optional JSON schema for `json` inputs (validated before execution). */
  schema: JsonSchema | null;
}

export interface OutputSpec {
  /** Path template, e.g. "{out}/estimate.json". */
  path: string;
  /** Deterministic checks from scripts/check_output.py (exists, json, csv:[...], sections:[...], ...). */
  checks: string[];
  /** Optional JSON schema the file must satisfy (parsed as JSON after the run). */
  schema: JsonSchema | null;
}

export interface StepSpec {
  step: string;
  kind: "script" | "llm";
  cmd?: string; stdout?: string; expect_exit?: number[];
  template?: string; context?: string[]; out?: string;
  skip_if_missing?: string[]; skip_if_present?: string[];
}

export type Provider = "none" | "anthropic" | "openai_compat";

export interface Manifest {
  manifest_version: 1;
  purpose: string;
  intended_users: string;
  usage_guidance: string;
  inputs: InputSpec[];
  outputs: OutputSpec[];
  run: StepSpec[];
  instructions_md: string;
  /** Files that travel with the version (repo: paths under the skill dir; authored: sf_files paths). */
  resources: string[];
  allowed_tools: ("script" | "llm")[];
  /** Names of workspace connections this skill needs (e.g. "anthropic"). */
  connections: string[];
  model_config: { provider: Provider; model: string; temperature: number; max_tokens: number };
  limits: { timeout_s: number; max_retries: number; max_tokens: number; max_cost_usd: number | null };
  release_criteria: { min_eval_pass_rate: number; require_approval: boolean };
  compat: { runner_version: string; runtime_version: string };
}

export const RUNNER_VERSION = "run_skill.py@inproc-1";
export const RUNTIME_VERSION = "vercel-python-3.12";
export const MAX_TIMEOUT_S = 55;
export const DEFAULT_MODEL = "claude-sonnet-4-5";
export const MODELS = ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-1"] as const;

export function emptyManifest(): Manifest {
  return {
    manifest_version: 1,
    purpose: "", intended_users: "", usage_guidance: "",
    inputs: [], outputs: [], run: [], instructions_md: "", resources: [],
    allowed_tools: ["script", "llm"], connections: [],
    model_config: { provider: "none", model: DEFAULT_MODEL, temperature: 0.2, max_tokens: 4000 },
    limits: { timeout_s: 50, max_retries: 0, max_tokens: 8000, max_cost_usd: null },
    release_criteria: { min_eval_pass_rate: 0.8, require_approval: true },
    compat: { runner_version: RUNNER_VERSION, runtime_version: RUNTIME_VERSION },
  };
}

export interface Problem { path: string; message: string }

const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Validates a manifest and returns a normalised copy or the list of problems. Never throws. */
export function validateManifest(raw: unknown): { ok: true; manifest: Manifest; problems: [] } | { ok: false; problems: Problem[] } {
  const problems: Problem[] = [];
  const bad = (path: string, message: string) => { problems.push({ path, message }); };
  if (!isObj(raw)) return { ok: false, problems: [{ path: "", message: "manifest must be a JSON object" }] };
  const m = raw;
  const base = emptyManifest();
  const str = (k: keyof Manifest, max: number) => {
    const v = m[k];
    if (v == null) return "";
    if (typeof v !== "string") { bad(k, "must be a string"); return ""; }
    if (v.length > max) bad(k, `longer than ${max} characters`);
    return v;
  };
  const out: Manifest = {
    ...base,
    purpose: str("purpose", 2000), intended_users: str("intended_users", 2000), usage_guidance: str("usage_guidance", 4000),
    instructions_md: str("instructions_md", 200_000),
  };
  if (m.manifest_version != null && m.manifest_version !== 1) bad("manifest_version", "only manifest_version 1 is supported");

  // inputs
  const names = new Set<string>();
  if (m.inputs != null && !Array.isArray(m.inputs)) bad("inputs", "must be an array");
  out.inputs = (Array.isArray(m.inputs) ? m.inputs : []).map((x, i) => {
    const p = `inputs[${i}]`;
    if (!isObj(x)) { bad(p, "must be an object"); return { name: `input${i}`, type: "string", required: false, from: "", default: null, flag: null, schema: null }; }
    const name = typeof x.name === "string" ? x.name : "";
    if (!NAME_RE.test(name)) bad(`${p}.name`, "must match ^[A-Za-z_][A-Za-z0-9_]*$ (max 64)");
    if (names.has(name)) bad(`${p}.name`, `duplicate input name "${name}"`);
    names.add(name);
    const type = (INPUT_TYPES as readonly string[]).includes(String(x.type)) ? (x.type as InputType) : null;
    if (!type) bad(`${p}.type`, `must be one of ${INPUT_TYPES.join(", ")}`);
    if (x.schema != null && !isObj(x.schema)) bad(`${p}.schema`, "must be an object (JSON schema) or null");
    if (x.schema != null && type !== "json") bad(`${p}.schema`, "schema is only supported on json inputs");
    return {
      name, type: type ?? "string", required: x.required === true, from: typeof x.from === "string" ? x.from : "",
      default: x.default == null || x.default === "" ? null : String(x.default),
      flag: typeof x.flag === "string" && x.flag ? x.flag : null,
      schema: isObj(x.schema) ? (x.schema as JsonSchema) : null,
    };
  });

  // outputs: under the run folder, either directly ({out}/…) or under a `path` input ({target}/…), which the
  // runtime always places inside the run folder
  const pathInputs = new Set(out.inputs.filter((i) => i.type === "path" || (i.type === "string" && (i.default ?? "").startsWith("{out}/"))).map((i) => i.name));
  if (m.outputs != null && !Array.isArray(m.outputs)) bad("outputs", "must be an array");
  out.outputs = (Array.isArray(m.outputs) ? m.outputs : []).map((x, i) => {
    const p = `outputs[${i}]`;
    if (!isObj(x)) { bad(p, "must be an object"); return { path: "", checks: [], schema: null }; }
    const path = typeof x.path === "string" ? x.path : "";
    const root = path.match(/^\{([A-Za-z_][A-Za-z0-9_]*)\}\//)?.[1];
    if (!root || (root !== "out" && !pathInputs.has(root))) bad(`${p}.path`, 'must start with "{out}/" or "{<path input>}/" (outputs live in the run folder)');
    if (/\.\./.test(path)) bad(`${p}.path`, 'must not contain ".."');
    const checks = Array.isArray(x.checks) ? x.checks.map((c) => (typeof c === "string" ? c : JSON.stringify(c))) : [];
    if (x.schema != null && !isObj(x.schema)) bad(`${p}.schema`, "must be an object (JSON schema) or null");
    return { path, checks, schema: isObj(x.schema) ? (x.schema as JsonSchema) : null };
  });
  if (out.outputs.length === 0) bad("outputs", "declare at least one output (a skill without an output contract cannot be validated)");

  // run steps
  if (m.run != null && !Array.isArray(m.run)) bad("run", "must be an array");
  const stepNames = new Set<string>();
  out.run = (Array.isArray(m.run) ? m.run : []).map((x, i) => {
    const p = `run[${i}]`;
    if (!isObj(x)) { bad(p, "must be an object"); return { step: `step${i}`, kind: "script" as const }; }
    const step = typeof x.step === "string" ? x.step : "";
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(step)) bad(`${p}.step`, "step name must be 1–64 of [A-Za-z0-9_-]");
    if (stepNames.has(step)) bad(`${p}.step`, `duplicate step "${step}"`);
    stepNames.add(step);
    const kind = x.kind === "llm" ? "llm" : x.kind === "script" ? "script" : null;
    if (!kind) bad(`${p}.kind`, 'must be "script" or "llm"');
    const s: StepSpec = { step, kind: kind ?? "script" };
    if (kind === "script") {
      if (typeof x.cmd !== "string" || !x.cmd.trim()) bad(`${p}.cmd`, "script steps need a cmd");
      else s.cmd = x.cmd;
      if (typeof x.stdout === "string" && x.stdout) s.stdout = x.stdout;
      if (x.expect_exit != null) {
        const ee = Array.isArray(x.expect_exit) ? x.expect_exit : [x.expect_exit];
        if (!ee.every((n) => Number.isInteger(n))) bad(`${p}.expect_exit`, "must be an integer or list of integers");
        else s.expect_exit = ee as number[];
      }
    } else if (kind === "llm") {
      if (typeof x.template !== "string" || !x.template) bad(`${p}.template`, "llm steps need a template file path");
      else s.template = x.template;
      if (typeof x.out !== "string" || !x.out.startsWith("{out}/")) bad(`${p}.out`, 'llm steps need an out path starting with "{out}/"');
      else s.out = x.out;
      if (x.context != null) {
        if (!Array.isArray(x.context) || !x.context.every((c) => typeof c === "string")) bad(`${p}.context`, "must be a list of file paths");
        else s.context = x.context as string[];
      }
    }
    for (const k of ["skip_if_missing", "skip_if_present"] as const) {
      if (x[k] != null) {
        if (!Array.isArray(x[k]) || !(x[k] as unknown[]).every((c) => typeof c === "string")) bad(`${p}.${k}`, "must be a list of input names");
        else s[k] = x[k] as string[];
      }
    }
    return s;
  });

  // tools / connections / resources
  const tools = Array.isArray(m.allowed_tools) ? m.allowed_tools : base.allowed_tools;
  if (!tools.every((t) => t === "script" || t === "llm")) bad("allowed_tools", 'entries must be "script" or "llm"');
  out.allowed_tools = tools.filter((t): t is "script" | "llm" => t === "script" || t === "llm");
  for (const s of out.run) if (!out.allowed_tools.includes(s.kind)) bad(`run`, `step "${s.step}" uses tool "${s.kind}" which allowed_tools does not permit`);
  const conns = Array.isArray(m.connections) ? m.connections : [];
  if (!conns.every((c) => typeof c === "string" && /^[a-z0-9_-]{1,40}$/.test(c))) bad("connections", "entries must be short lowercase names");
  out.connections = conns.filter((c): c is string => typeof c === "string");
  const res = Array.isArray(m.resources) ? m.resources : [];
  if (!res.every((r) => typeof r === "string" && !/\.\./.test(r))) bad("resources", 'entries must be relative paths without ".."');
  out.resources = res.filter((r): r is string => typeof r === "string");

  // model config
  const mc = isObj(m.model_config) ? m.model_config : {};
  const provider = mc.provider === "anthropic" || mc.provider === "openai_compat" ? mc.provider : mc.provider == null || mc.provider === "none" ? "none" : null;
  if (!provider) bad("model_config.provider", 'must be "none", "anthropic" or "openai_compat"');
  const temperature = mc.temperature == null ? base.model_config.temperature : mc.temperature;
  if (!isNum(temperature) || temperature < 0 || temperature > 1) bad("model_config.temperature", "must be a number between 0 and 1");
  const maxTok = mc.max_tokens == null ? base.model_config.max_tokens : mc.max_tokens;
  if (!Number.isInteger(maxTok) || (maxTok as number) < 1 || (maxTok as number) > 32000) bad("model_config.max_tokens", "must be an integer 1–32000");
  out.model_config = {
    provider: provider ?? "none", model: typeof mc.model === "string" && mc.model ? mc.model : DEFAULT_MODEL,
    temperature: isNum(temperature) ? temperature : 0.2, max_tokens: Number.isInteger(maxTok) ? (maxTok as number) : 4000,
  };
  const hasLlm = out.run.some((s) => s.kind === "llm");
  if (hasLlm && out.model_config.provider === "none") bad("model_config.provider", 'this skill has llm steps; with provider "none" they are skipped and their checks fail (set "anthropic" or "openai_compat" to run them)');
  if (out.model_config.provider !== "none" && !out.connections.includes(out.model_config.provider)) out.connections.push(out.model_config.provider);
  out.connections = out.connections.filter((c) => !(["anthropic", "openai_compat"].includes(c) && c !== out.model_config.provider));

  // limits
  const lim = isObj(m.limits) ? m.limits : {};
  const timeout = lim.timeout_s == null ? base.limits.timeout_s : lim.timeout_s;
  if (!isNum(timeout) || timeout < 1 || timeout > MAX_TIMEOUT_S) bad("limits.timeout_s", `must be between 1 and ${MAX_TIMEOUT_S} seconds (the serverless runtime's ceiling)`);
  const retries = lim.max_retries == null ? 0 : lim.max_retries;
  if (!Number.isInteger(retries) || (retries as number) < 0 || (retries as number) > 2) bad("limits.max_retries", "must be 0, 1 or 2");
  const lt = lim.max_tokens == null ? base.limits.max_tokens : lim.max_tokens;
  if (!Number.isInteger(lt) || (lt as number) < 1) bad("limits.max_tokens", "must be a positive integer");
  const cost = lim.max_cost_usd == null ? null : lim.max_cost_usd;
  if (cost != null && (!isNum(cost) || cost < 0)) bad("limits.max_cost_usd", "must be a non-negative number or null");
  out.limits = {
    timeout_s: isNum(timeout) ? Math.floor(timeout) : 50, max_retries: Number.isInteger(retries) ? (retries as number) : 0,
    max_tokens: Number.isInteger(lt) ? (lt as number) : 8000, max_cost_usd: isNum(cost) ? cost : null,
  };
  if (out.model_config.max_tokens > out.limits.max_tokens) bad("model_config.max_tokens", "exceeds limits.max_tokens");

  // release criteria
  const rc = isObj(m.release_criteria) ? m.release_criteria : {};
  const minRate = rc.min_eval_pass_rate == null ? base.release_criteria.min_eval_pass_rate : rc.min_eval_pass_rate;
  if (!isNum(minRate) || minRate < 0 || minRate > 1) bad("release_criteria.min_eval_pass_rate", "must be between 0 (no gate) and 1");
  out.release_criteria = { min_eval_pass_rate: isNum(minRate) ? minRate : 0.8, require_approval: rc.require_approval !== false };

  // compat
  const cp = isObj(m.compat) ? m.compat : {};
  out.compat = {
    runner_version: typeof cp.runner_version === "string" && cp.runner_version ? cp.runner_version : RUNNER_VERSION,
    runtime_version: typeof cp.runtime_version === "string" && cp.runtime_version ? cp.runtime_version : RUNTIME_VERSION,
  };

  if (problems.length) return { ok: false, problems };
  return { ok: true, manifest: out, problems: [] };
}

/** Canonical JSON: keys sorted recursively, no whitespace, so equal manifests hash equal. */
export function canonicalJson(v: unknown): string {
  if (v === null || typeof v !== "object") return JSON.stringify(v === undefined ? null : v);
  if (Array.isArray(v)) return "[" + v.map(canonicalJson).join(",") + "]";
  const o = v as Record<string, unknown>;
  return "{" + Object.keys(o).filter((k) => o[k] !== undefined).sort().map((k) => JSON.stringify(k) + ":" + canonicalJson(o[k])).join(",") + "}";
}

/** The input names the runtime will accept for this manifest. */
export const inputNames = (m: Pick<Manifest, "inputs">) => m.inputs.map((i) => i.name);

/** What the skill needs from the workspace to run every step. */
export function requirements(m: Manifest): { tools: string[]; connections: string[]; llm: boolean } {
  const tools = [...new Set(m.run.map((s) => s.kind))];
  return { tools, connections: m.connections, llm: m.run.some((s) => s.kind === "llm") };
}
