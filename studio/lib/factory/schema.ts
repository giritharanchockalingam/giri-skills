/* Input validation before a run and output-contract validation after it. Pure module.
 *
 * validateJson: a deliberately small JSON-schema subset (type, properties, required, items, enum, min/max,
 * minLength/maxLength, pattern, additionalProperties) — no dependency, no $ref, no oneOf.
 */
import { TEXT_INPUT_TYPES, type JsonSchema, type Manifest, type InputSpec, type Problem } from "./manifest.ts";

export type { Problem };

export function validateJson(schema: JsonSchema, value: unknown, path = "$"): Problem[] {
  const out: Problem[] = [];
  const t = schema.type;
  const typeOf = (v: unknown) => v === null ? "null" : Array.isArray(v) ? "array" : typeof v === "number" ? (Number.isInteger(v) ? "integer" : "number") : typeof v;
  const actual = typeOf(value);
  if (t) {
    const ok = t === actual || (t === "number" && actual === "integer");
    if (!ok) { out.push({ path, message: `expected ${t}, got ${actual}` }); return out; }
  }
  if (schema.enum && !schema.enum.some((e) => e === value)) out.push({ path, message: `must be one of ${schema.enum.map((e) => JSON.stringify(e)).join(", ")}` });
  if (typeof value === "number") {
    if (schema.minimum != null && value < schema.minimum) out.push({ path, message: `must be >= ${schema.minimum}` });
    if (schema.maximum != null && value > schema.maximum) out.push({ path, message: `must be <= ${schema.maximum}` });
  }
  if (typeof value === "string") {
    if (schema.minLength != null && value.length < schema.minLength) out.push({ path, message: `must be at least ${schema.minLength} characters` });
    if (schema.maxLength != null && value.length > schema.maxLength) out.push({ path, message: `must be at most ${schema.maxLength} characters` });
    if (schema.pattern) {
      let re: RegExp | null = null;
      try { re = new RegExp(schema.pattern); } catch { out.push({ path, message: `schema pattern is invalid: ${schema.pattern}` }); }
      if (re && !re.test(value)) out.push({ path, message: `must match /${schema.pattern}/` });
    }
  }
  if (Array.isArray(value) && schema.items) value.forEach((v, i) => out.push(...validateJson(schema.items!, v, `${path}[${i}]`)));
  if (actual === "object" && value && typeof value === "object") {
    const o = value as Record<string, unknown>;
    for (const r of schema.required ?? []) if (!(r in o)) out.push({ path: `${path}.${r}`, message: "is required" });
    for (const [k, sub] of Object.entries(schema.properties ?? {})) if (k in o) out.push(...validateJson(sub, o[k], `${path}.${k}`));
    if (schema.additionalProperties === false) {
      for (const k of Object.keys(o)) if (!(schema.properties && k in schema.properties)) out.push({ path: `${path}.${k}`, message: "is not an allowed property" });
    }
  }
  return out;
}

/** What a caller may send per input: file-content text for text types, a value for the rest. */
export type RunInput = { kind: "text"; content: string; ext?: string } | { kind: "value"; value: string } | { kind: "fixture"; path: string };

export interface ValidatedInputs { inputs: Record<string, RunInput>; problems: Problem[]; missing: string[] }

const MAX_TEXT_BYTES = 2_000_000;

/**
 * Validates caller inputs against the manifest's input specs BEFORE anything executes.
 * Accepts either structured RunInput values or plain JSON values (string / number / boolean / object)
 * as the consumer API does. Unknown names are rejected; required inputs must be present; json inputs must
 * parse and satisfy their schema; csv inputs need a header line. `dir` inputs are not accepted over HTTP.
 */
export function validateInputs(manifest: Pick<Manifest, "inputs">, raw: unknown, opts: { allowFixtures?: boolean } = {}): ValidatedInputs {
  const problems: Problem[] = [];
  const inputs: Record<string, RunInput> = {};
  const missing: string[] = [];
  if (raw != null && (typeof raw !== "object" || Array.isArray(raw))) return { inputs, missing, problems: [{ path: "inputs", message: "must be an object of name → value" }] };
  const given = (raw ?? {}) as Record<string, unknown>;
  const specs = new Map(manifest.inputs.map((i) => [i.name, i]));
  for (const k of Object.keys(given)) if (!specs.has(k)) problems.push({ path: `inputs.${k}`, message: `unknown input; declared inputs: ${[...specs.keys()].join(", ") || "(none)"}` });
  for (const spec of manifest.inputs) {
    const v = given[spec.name];
    const empty = v == null || v === "" || (typeof v === "object" && !Array.isArray(v) && (v as { kind?: string; content?: string }).kind === "text" && !(v as { content?: string }).content?.trim());
    if (empty) { if (spec.required && spec.default == null) missing.push(spec.name); continue; }
    const r = normalise(spec, v, opts.allowFixtures === true);
    if ("problem" in r) { problems.push({ path: `inputs.${spec.name}`, message: r.problem }); continue; }
    const p = check(spec, r.input);
    if (p) { problems.push({ path: `inputs.${spec.name}`, message: p }); continue; }
    inputs[spec.name] = r.input;
  }
  return { inputs, problems, missing };
}

function normalise(spec: InputSpec, v: unknown, allowFixtures: boolean): { input: RunInput } | { problem: string } {
  const isText = (TEXT_INPUT_TYPES as readonly string[]).includes(spec.type);
  if (typeof v === "object" && v !== null && !Array.isArray(v) && "kind" in v) {
    const o = v as Record<string, unknown>;
    if (o.kind === "fixture") {
      if (!allowFixtures) return { problem: "fixture references are only accepted from evaluation cases" };
      if (typeof o.path !== "string" || !/^evals\/fixtures\/[A-Za-z0-9._\/-]+$/.test(o.path) || o.path.includes("..")) return { problem: "fixture path must be under evals/fixtures/" };
      return { input: { kind: "fixture", path: o.path } };
    }
    if (o.kind === "text") return typeof o.content === "string" ? { input: { kind: "text", content: o.content, ext: typeof o.ext === "string" ? o.ext : undefined } } : { problem: "text input needs string content" };
    if (o.kind === "value") return typeof o.value === "string" ? { input: { kind: "value", value: o.value } } : { problem: "value input needs a string value" };
    return { problem: "unknown input kind" };
  }
  if (spec.type === "dir") return { problem: "directory inputs cannot be supplied over HTTP (use a file input or a fixture in an evaluation case)" };
  if (isText) {
    if (spec.type === "json" && typeof v === "object") return { input: { kind: "text", content: JSON.stringify(v, null, 2) } };
    if (typeof v !== "string") return { problem: `expected file content (string) for a ${spec.type} input` };
    return { input: { kind: "text", content: v } };
  }
  if (spec.type === "flag") {
    if (typeof v === "boolean") return { input: { kind: "value", value: v ? "true" : "false" } };
    if (typeof v === "string" && ["true", "false", "1", "0", "yes", "no", "on", "off"].includes(v.toLowerCase())) return { input: { kind: "value", value: v } };
    return { problem: "flag inputs take true or false" };
  }
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return { input: { kind: "value", value: String(v) } };
  return { problem: `expected a scalar value for a ${spec.type} input` };
}

function check(spec: InputSpec, input: RunInput): string | null {
  if (input.kind === "text") {
    if (input.content.length > MAX_TEXT_BYTES) return `larger than ${MAX_TEXT_BYTES / 1e6} MB`;
    if (spec.type === "json") {
      let parsed: unknown;
      try { parsed = JSON.parse(input.content); } catch (e) { return `is not valid JSON (${(e as Error).message})`; }
      if (spec.schema) {
        const ps = validateJson(spec.schema, parsed);
        if (ps.length) return ps.map((p) => `${p.path} ${p.message}`).join("; ");
      }
    }
    if (spec.type === "csv") {
      const first = input.content.split(/\r?\n/).find((l) => l.trim());
      if (!first || !first.includes(",")) return "CSV needs a header line with at least two columns";
    }
  }
  if (input.kind === "value") {
    if (spec.type === "path" && /\.\./.test(input.value)) return 'must not contain ".."';
    if (input.value.length > 4000) return "longer than 4000 characters";
  }
  return null;
}

/** A non-secret, loggable description of what was sent: names, sizes and content hashes (hash supplied by caller). */
export interface InputRef { name: string; kind: RunInput["kind"]; bytes: number; sha256: string | null; value?: string }
export function describeInputs(inputs: Record<string, RunInput>, sha256: (s: string) => string): InputRef[] {
  return Object.entries(inputs).map(([name, i]) => {
    if (i.kind === "text") return { name, kind: i.kind, bytes: byteLength(i.content), sha256: sha256(i.content) };
    if (i.kind === "fixture") return { name, kind: i.kind, bytes: 0, sha256: null, value: i.path };
    return { name, kind: i.kind, bytes: byteLength(i.value), sha256: sha256(i.value), value: i.value.length > 200 ? i.value.slice(0, 200) + "…" : i.value };
  });
}
const byteLength = (s: string) => new TextEncoder().encode(s).length;

/* ───────────── output contract (after the run) ───────────── */

export interface OutputFile { path: string; bytes: number; sha256: string; content_text: string | null }
export interface ContractResult { ok: boolean; problems: Problem[] }

/**
 * Every declared output must exist in the run's output set (non-empty); outputs with a schema must parse
 * as JSON and satisfy it. Paths are compared relative to the run folder ("{out}/x.json" ↔ "x.json").
 */
export function validateOutputContract(manifest: Pick<Manifest, "outputs">, files: OutputFile[], resolveInput?: (name: string) => string | null): ContractResult {
  const problems: Problem[] = [];
  const byRel = new Map(files.map((f) => [f.path.replace(/^.*?\{out\}\//, "").replace(/^\/+/, ""), f]));
  for (const o of manifest.outputs) {
    // "{out}/x" → "x"; "{target}/x" → "<target's folder under the run folder>/x" (default: "target/x")
    const rel = o.path.replace(/^\{out\}\//, "").replace(/^\{([A-Za-z_][A-Za-z0-9_]*)\}\//, (_m, name: string) => {
      const r = resolveInput?.(name);
      return r == null ? `${name}/` : r === "" ? "" : `${r.replace(/\/+$/, "")}/`;
    });
    const f = byRel.get(rel);
    if (!f || f.bytes === 0) { problems.push({ path: rel, message: "declared output was not produced" }); continue; }
    if (o.schema) {
      if (f.content_text == null) { problems.push({ path: rel, message: "too large to validate against its schema" }); continue; }
      let parsed: unknown;
      try { parsed = JSON.parse(f.content_text); } catch { problems.push({ path: rel, message: "is not valid JSON" }); continue; }
      for (const p of validateJson(o.schema, parsed)) problems.push({ path: `${rel}:${p.path}`, message: p.message });
    }
  }
  return { ok: problems.length === 0, problems };
}
