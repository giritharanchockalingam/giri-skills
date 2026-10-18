/* Import from repo: a wired skill (data/skills.json, i.e. its SKILL.md metadata.agent block + evals.json) → a factory
 * manifest and evaluation cases. This is real repository data, not seed data. Pure module. */
import { defaultLlmProvider } from "./providers.ts";
import { emptyManifest, validateManifest, type Manifest, type InputType, type StepSpec, type Problem } from "./manifest.ts";

export interface RepoAgentInput { name: string; type: string; required: boolean; from: string; default: string | null; flag: string | null; copy?: boolean }
export interface RepoAgentOutput { path: string; checks: string[] }
export interface RepoAgentCase { id: string; prompt: string; inputs: Record<string, string>; assume: Record<string, string>; checks: unknown[]; expected: string[] }
export interface RepoSkill {
  id: string; domain: string; name: string; description: string;
  metadata: Record<string, string>;
  agent: { inputs: RepoAgentInput[]; run?: Record<string, unknown>[]; steps: { step: string; kind: string }[]; outputs: RepoAgentOutput[] } | null;
  files: { references: string[]; assets: string[]; scripts: string[] };
  agentCases?: RepoAgentCase[];
  bodyMd?: string;
}

const toIntList = (v: unknown): number[] | undefined => {
  if (v == null) return undefined;
  const arr = Array.isArray(v) ? v : [v];
  const nums = arr.map((x) => Number(x)).filter((n) => Number.isInteger(n));
  return nums.length ? nums : undefined;
};
const toStrList = (v: unknown): string[] | undefined => (Array.isArray(v) ? v.map(String) : typeof v === "string" ? [v] : undefined);

export function manifestFromRepoSkill(s: RepoSkill): { ok: true; manifest: Manifest } | { ok: false; problems: Problem[] } {
  if (!s.agent) return { ok: false, problems: [{ path: "agent", message: `${s.id} has no metadata.agent block — it cannot run as a skill` }] };
  const base = emptyManifest();
  const run: StepSpec[] = (s.agent.run ?? []).map((o) => {
    const st: StepSpec = { step: String(o.step ?? ""), kind: o.kind === "llm" ? "llm" : "script" };
    if (typeof o.cmd === "string") st.cmd = o.cmd;
    if (typeof o.stdout === "string") st.stdout = o.stdout;
    const ee = toIntList(o.expect_exit); if (ee) st.expect_exit = ee;
    if (typeof o.template === "string") st.template = o.template;
    const ctx = toStrList(o.context); if (ctx) st.context = ctx;
    if (typeof o.out === "string") st.out = o.out;
    const sm = toStrList(o.skip_if_missing); if (sm) st.skip_if_missing = sm;
    const sp = toStrList(o.skip_if_present); if (sp) st.skip_if_present = sp;
    return st;
  });
  const hasLlm = run.some((r) => r.kind === "llm");
  const llm = defaultLlmProvider();
  const draft: Manifest = {
    ...base,
    purpose: s.description,
    intended_users: "",
    usage_guidance: `Imported from the repository skill ${s.id} (SKILL.md v${s.metadata.version ?? "?"}). Runs scripts/run_skill.py with the inputs below.`,
    inputs: s.agent.inputs.map((i) => ({
      name: i.name, type: (i.type || "string") as InputType, required: i.required === true, from: i.from ?? "",
      default: i.default == null || i.default === "" ? null : String(i.default), flag: i.flag ?? null, schema: null,
    })),
    outputs: s.agent.outputs.map((o) => ({ path: o.path, checks: o.checks ?? [], schema: null })),
    run,
    instructions_md: s.bodyMd ?? "",
    resources: [
      "SKILL.md",
      ...s.files.scripts.map((f) => `scripts/${f}`), ...s.files.assets.map((f) => `assets/${f}`), ...s.files.references.map((f) => `references/${f}`),
    ],
    allowed_tools: hasLlm ? ["script", "llm"] : ["script"],
    connections: hasLlm ? [llm.provider] : [],
    model_config: { ...base.model_config, provider: hasLlm ? llm.provider : "none", ...(hasLlm && llm.model ? { model: llm.model } : {}) },
  };
  const v = validateManifest(draft);
  if (!v.ok) return { ok: false, problems: v.problems };
  return { ok: true, manifest: v.manifest };
}

export interface ImportedCase { name: string; inputs: Record<string, unknown>; checks: unknown[]; expected: Record<string, unknown>; notes: string }

/** evals.json agent cases → evaluation cases. Fixture paths (evals/fixtures/…) stay references the runtime resolves. */
export function casesFromRepoSkill(s: RepoSkill): ImportedCase[] {
  return (s.agentCases ?? []).map((c) => ({
    name: c.id,
    inputs: Object.fromEntries(Object.entries(c.inputs).map(([k, v]) => [k, v.startsWith("evals/") ? { kind: "fixture", path: v } : v])),
    checks: c.checks,
    expected: { assume: c.assume, expected: c.expected },
    notes: c.prompt,
  }));
}

/** Workspace slug for a repo skill: the skill name (unique across domains in this repo); falls back to domain-name. */
export const repoSlug = (s: Pick<RepoSkill, "name" | "domain">, taken: Set<string>) => (taken.has(s.name) ? `${s.domain}-${s.name}` : s.name);
