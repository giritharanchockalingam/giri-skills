/* Composed agents — the pure core shared by the Builder UI, the API and tests (no I/O here).
 * An agent is configuration: inputs, ordered steps (skill | compose | approval) and outputs. The same rules as
 * scripts/run_agent.py validate() apply, so a spec that validates here runs there and vice versa. */

export type AgentInputType = "string" | "csv" | "json" | "md" | "txt" | "file" | "args" | "flag";
export interface AgentInputDecl { name: string; type: string; required: boolean; from?: string }
export interface SkillStep { id: string; skill: string; inputs: Record<string, string>; assume?: Record<string, string>; gate?: boolean; continue_on_fail?: boolean }
export interface ComposeStep { id: string; compose: { out: string; format: "kv-csv" | "json"; rows: Record<string, string>; include?: string } }
export interface ApprovalStep { id: string; approval: { role: string; note?: string } }
export type AgentStepSpec = SkillStep | ComposeStep | ApprovalStep;
export interface AgentSpec {
  name: string; version?: string; description: string; adlc_stage?: string | string[];
  inputs: AgentInputDecl[];
  config?: { provider?: "auto" | "none"; on_fail?: "stop" };
  steps: AgentStepSpec[];
  outputs?: string[];
}

/** What the Builder knows about a catalog skill (from data/skills.json). */
export interface CatalogSkill { id: string; name: string; stage: string | null; description: string; inputs: { name: string; type: string; required: boolean; from: string; default?: string | null }[]; outputs: string[] }

export const isSkill = (s: AgentStepSpec): s is SkillStep => "skill" in s;
export const isCompose = (s: AgentStepSpec): s is ComposeStep => "compose" in s;
export const isApproval = (s: AgentStepSpec): s is ApprovalStep => "approval" in s;
export const stepKind = (s: AgentStepSpec) => (isSkill(s) ? "skill" : isCompose(s) ? "compose" : "approval");

export const REF_RE = /^\$(in)\.([A-Za-z_][\w-]*)$|^\$steps\.([A-Za-z_][\w-]*):([^#]+?)(?:#([\w.\-[\]]+))?$/;
const ID_RE = /^[a-z][a-z0-9-]{0,40}$/;
export type Ref = { kind: "in"; name: string } | { kind: "step"; step: string; file: string; key: string | null } | { kind: "literal"; value: string };
export function parseRef(v: string): Ref | null {
  if (!v.startsWith("$")) return { kind: "literal", value: v };
  const m = REF_RE.exec(v);
  if (!m) return null;
  return m[1] ? { kind: "in", name: m[2] } : { kind: "step", step: m[3], file: m[4], key: m[5] ?? null };
}

const refsOf = (v: unknown): string[] =>
  typeof v === "string" ? (v.startsWith("$") ? [v] : []) : Array.isArray(v) ? v.flatMap(refsOf) : v && typeof v === "object" ? Object.values(v).flatMap(refsOf) : [];

export const fileOutputs = (c: CatalogSkill) => c.outputs.map((p) => p.replace(/^\{out\}\//, ""));

/** Same rules as run_agent.py validate(). Every problem is reported; an empty list means runnable. */
export function validateAgentSpec(spec: AgentSpec, catalog: Map<string, CatalogSkill>): string[] {
  const problems: string[] = [];
  for (const k of ["name", "description"] as const) if (!spec[k]?.toString().trim()) problems.push(`missing '${k}'`);
  if (!spec.steps?.length) problems.push("the agent has no steps");
  const inputs = new Map((spec.inputs ?? []).map((i) => [i.name, i]));
  const files = new Map<string, Set<string>>();
  const seen: string[] = [];
  (spec.steps ?? []).forEach((step, idx) => {
    const where = `step ${idx + 1} (${step.id || "?"})`;
    if (!ID_RE.test(step.id ?? "")) problems.push(`${where}: id must be lower-kebab-case`);
    if (seen.includes(step.id)) problems.push(`${where}: duplicate id`);
    const kinds = ["skill", "compose", "approval"].filter((k) => k in step);
    if (kinds.length !== 1) { problems.push(`${where}: needs exactly one of skill, compose, approval`); seen.push(step.id); return; }
    const refs = [...refsOf((step as SkillStep).inputs), ...refsOf((step as ComposeStep).compose), ...refsOf((step as SkillStep).assume)];
    for (const r of refs) {
      const p = parseRef(r);
      if (!p) problems.push(`${where}: bad reference ${JSON.stringify(r)}`);
      else if (p.kind === "in" && !inputs.has(p.name)) problems.push(`${where}: ${r} is not a declared agent input`);
      else if (p.kind === "step") {
        if (!seen.includes(p.step)) problems.push(`${where}: ${r} refers to a step that does not run before it`);
        else if (files.has(p.step) && !files.get(p.step)!.has(p.file)) problems.push(`${where}: ${r} — step '${p.step}' does not declare '${p.file}' (it declares ${[...files.get(p.step)!].sort().join(", ") || "nothing"})`);
      }
    }
    if (isSkill(step)) {
      const c = catalog.get(step.skill);
      if (!c) problems.push(`${where}: skill ${step.skill} not found`);
      else {
        const declared = new Map(c.inputs.map((i) => [i.name, i]));
        const mapped = new Set([...Object.keys(step.inputs ?? {}), ...Object.keys(step.assume ?? {})]);
        for (const n of mapped) if (!declared.has(n)) problems.push(`${where}: ${step.skill} has no input '${n}' (declares ${[...declared.keys()].sort().join(", ")})`);
        for (const [n, i] of declared) if (i.required && !mapped.has(n) && !i.default) problems.push(`${where}: required input '${n}' of ${step.skill} is not mapped`);
        files.set(step.id, new Set(fileOutputs(c)));
      }
    } else if (isCompose(step)) {
      const c = step.compose;
      if (!c?.out || !["kv-csv", "json"].includes(c.format) || !c.rows || typeof c.rows !== "object") problems.push(`${where}: compose needs out, format kv-csv|json and rows{}`);
      files.set(step.id, new Set([String(c?.out ?? "")]));
    } else if (isApproval(step)) {
      if (!step.approval?.role?.trim()) problems.push(`${where}: approval needs a role`);
      files.set(step.id, new Set());
    }
    seen.push(step.id);
  });
  for (const r of refsOf(spec.outputs)) {
    const p = parseRef(r);
    if (!p || (p.kind === "step" && !seen.includes(p.step))) problems.push(`outputs: bad reference ${JSON.stringify(r)}`);
  }
  return problems;
}

const EXT_OF: Record<string, string[]> = { csv: ["csv"], json: ["json"], md: ["md"], txt: ["txt", "md"], file: ["csv", "json", "jsonl", "md", "txt"] };
const stem = (f: string) => f.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9]/g, "");
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

/** Suggest a source for each input of a newly added skill step: an earlier step's output whose name matches the input
 *  (e.g. input `estimate` ← estimate.md, `value_case` ← value-case.md), else an agent input of the same name
 *  (created with the skill's own type and required flag). Returns the mapping and any agent inputs to add. */
export function autoWire(spec: AgentSpec, skill: CatalogSkill, catalog: Map<string, CatalogSkill>): { inputs: Record<string, string>; newAgentInputs: AgentInputDecl[] } {
  const earlier: { step: string; file: string }[] = [];
  for (const s of spec.steps) {
    if (isSkill(s)) { const c = catalog.get(s.skill); if (c) for (const f of fileOutputs(c)) earlier.push({ step: s.id, file: f }); }
    else if (isCompose(s)) earlier.push({ step: s.id, file: s.compose.out });
  }
  const mapping: Record<string, string> = {};
  const add: AgentInputDecl[] = [];
  const existing = new Set(spec.inputs.map((i) => i.name));
  for (const i of skill.inputs) {
    const exts = EXT_OF[i.type] ?? [];
    const candidates = earlier.filter((e) => exts.includes(e.file.split(".").pop() ?? "") && (stem(e.file).includes(norm(i.name)) || norm(i.name).includes(stem(e.file))));
    if (candidates.length) {
      // prefer an exact name match (estimate ← estimate.md over estimate-memo.md), then the most recent step
      const exact = candidates.filter((e) => stem(e.file) === norm(i.name));
      const pool = exact.length ? exact : candidates;
      const lastStep = pool[pool.length - 1].step;
      const c = pool.find((e) => e.step === lastStep)!;
      mapping[i.name] = `$steps.${c.step}:${c.file}`;
      continue;
    }
    if (!i.required && !existing.has(i.name)) continue; // optional and nothing to wire: leave it to the skill's own rule
    mapping[i.name] = `$in.${i.name}`;
    if (!existing.has(i.name) && !add.some((a) => a.name === i.name)) add.push({ name: i.name, type: i.type, required: i.required, from: i.from });
  }
  return { inputs: mapping, newAgentInputs: add };
}

/** A unique, valid step id derived from a skill name ("presales/effort-estimator" → "effort-estimator", "-2"…). */
export function newStepId(spec: AgentSpec, base: string): string {
  const b = (base.split("/").pop() ?? "step").toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/^-+|-+$/g, "").slice(0, 36) || "step";
  const root = /^[a-z]/.test(b) ? b : `s-${b}`;
  let id = root, n = 2;
  while (spec.steps.some((s) => s.id === id)) id = `${root}-${n++}`;
  return id;
}

/** Agent inputs no step references any more (safe to drop after a step is removed). */
export function unusedInputs(spec: AgentSpec): string[] {
  const used = new Set(spec.steps.flatMap((s) => refsOf(isSkill(s) ? s.inputs : isCompose(s) ? s.compose : {})).map(parseRef).filter((r): r is Extract<Ref, { kind: "in" }> => r?.kind === "in").map((r) => r.name));
  return spec.inputs.map((i) => i.name).filter((n) => !used.has(n));
}

// ───────────────────────── run-time reference resolution (state lives in sf_agent_runs) ─────────────────────────

export type StoredInput = { kind: "text"; content: string; ext?: string } | { kind: "value"; value: string };
export interface StoredFile { path: string; bytes: number; sha256: string; content_text: string | null }
export interface StepRecord {
  id: string; kind: "skill" | "compose" | "approval";
  status: "ok" | "approved" | "failed" | "blocked" | "awaiting_approval" | "needs_input" | "skipped";
  skill?: string; run_id?: string; checks_passed?: number; checks_total?: number; files?: StoredFile[];
  /** Failed checks with their evidence, so a failed step is reviewable without re-running it. */
  failed_checks?: { check: string; path: string; evidence: string }[];
  error?: string | null; duration_ms?: number; cost_usd?: number | null; provider?: string | null; model?: string | null;
  role?: string; note?: string; approver_id?: string; approver_email?: string; approval_note?: string; at?: string;
}

export class RefError extends Error {}

function dig(data: unknown, dotted: string): string {
  let cur: unknown = data;
  for (const part of dotted.split(".")) {
    if (Array.isArray(cur) && /^\d+$/.test(part) && Number(part) < cur.length) cur = cur[Number(part)];
    else if (cur && typeof cur === "object" && part in (cur as Record<string, unknown>)) cur = (cur as Record<string, unknown>)[part];
    else throw new RefError(`key '${dotted}' not found`);
  }
  if (cur instanceof NumText) return cur.text;
  if (cur !== null && typeof cur === "object") throw new RefError(`key '${dotted}' is not a single value`);
  // Python json + str() spelling, so composed values match the CLI byte for byte (True/False/None, 1.0 stays 1.0)
  return cur === true ? "True" : cur === false ? "False" : cur === null ? "None" : String(cur);
}

/** A JSON number kept as written ("1.0", "0.8421"): JSON.parse would turn 1.0 into 1. */
class NumText { readonly text: string; constructor(text: string) { this.text = text; } }
function parseJsonKeepNumbers(text: string): unknown {
  // walk the text, wrapping every number token in a string marker, then revive markers into NumText
  let out = "", i = 0, inStr = false;
  while (i < text.length) {
    const ch = text[i];
    if (inStr) { out += ch; if (ch === "\\") { out += text[i + 1] ?? ""; i += 2; continue; } if (ch === '"') inStr = false; i++; continue; }
    if (ch === '"') { inStr = true; out += ch; i++; continue; }
    const m = /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(text.slice(i));
    if (m && /[\s,:[]/.test(out.trimEnd().slice(-1) || "[")) { out += JSON.stringify("\u0000num:" + m[0]); i += m[0].length; continue; }
    out += ch; i++;
  }
  return JSON.parse(out, (_k, v) => (typeof v === "string" && v.startsWith("\u0000num:") ? new NumText(v.slice(5)) : v));
}

/** Resolve a reference to a skill input: agent input, an earlier step's file, a value inside its JSON, or a literal. */
export function resolveRef(ref: string, inputs: Record<string, StoredInput>, steps: StepRecord[]): StoredInput {
  const p = parseRef(ref);
  if (!p) throw new RefError(`bad reference ${ref}`);
  if (p.kind === "literal") return { kind: "value", value: p.value };
  if (p.kind === "in") {
    const v = inputs[p.name];
    if (!v) throw new RefError(`agent input '${p.name}' not given`);
    return v;
  }
  const rec = steps.find((s) => s.id === p.step);
  if (!rec) throw new RefError(`step '${p.step}' has not run`);
  const f = rec.files?.find((x) => x.path === p.file);
  if (!f || f.content_text == null) throw new RefError(`step '${p.step}' did not write ${p.file}`);
  if (!p.key) return { kind: "text", content: f.content_text, ext: p.file.split(".").pop() };
  let data: unknown;
  try { data = parseJsonKeepNumbers(f.content_text); } catch (e) { throw new RefError(`${p.file} is not JSON: ${(e as Error).message}`); }
  return { kind: "value", value: dig(data, p.key) };
}

const csvCell = (v: string) => (/[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = []; let row: string[] = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') q = false; else cell += ch; }
    else if (ch === '"') q = true; else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") { if (ch === "\r" && text[i + 1] === "\n") i++; row.push(cell); rows.push(row); row = []; cell = ""; }
    else cell += ch;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  const [head, ...body] = rows.filter((r) => r.length && !(r.length === 1 && r[0] === ""));
  return (body ?? []).map((r) => Object.fromEntries((head ?? []).map((h, i) => [h, r[i] ?? ""])));
}

/** Same output as run_agent.py do_compose(): kv-csv (key,value,source,notes) or json; `include` adds owner rows. */
export function composeFile(c: ComposeStep["compose"], inputs: Record<string, StoredInput>, steps: StepRecord[]): { path: string; content: string } {
  const rows: [string, string][] = Object.entries(c.rows).map(([k, ref]) => {
    const r = resolveRef(ref, inputs, steps);
    return [k, r.kind === "value" ? r.value : r.content];
  });
  if (c.format === "json") return { path: c.out, content: JSON.stringify(Object.fromEntries(rows), null, 2) + "\n" };
  const lines = ["key,value,source,notes"];
  for (const [k, v] of rows) { const src = c.rows[k]; lines.push([k, v, src.startsWith("$") ? src : "agent config", "composed by agent"].map(csvCell).join(",")); }
  if (c.include) {
    const inc = resolveRef(c.include, inputs, steps);
    const text = inc.kind === "text" ? inc.content : inc.value;
    const keys = new Set(rows.map(([k]) => k));
    const body = text.split(/\r?\n/).filter((l) => !l.startsWith("#")).join("\n");
    for (const r of parseCsv(body)) if (r.key && !keys.has(r.key)) lines.push([r.key, r.value ?? "", r.source || "include", r.notes ?? ""].map(csvCell).join(","));
  }
  return { path: c.out, content: lines.join("\n") + "\n" };
}
