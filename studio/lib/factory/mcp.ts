/* MCP (Model Context Protocol) server core — Streamable HTTP transport, stateless, JSON responses (no SSE stream).
 *
 * One endpoint per scope, each its own MCP server:
 *   /api/mcp                 every PUBLISHED skill in the API key's workspace
 *   /api/mcp/role/<slug>     the skills of one role   (the workspace's published, tailored role; else the template)
 *   /api/mcp/team/<slug>     the skills of one team   (union of its members' roles)
 *   /api/mcp/stage/<id>      the skills of one lifecycle stage
 * Tools: one per published skill in scope (its input contract as JSON Schema) + `find_skill` + `get_run`.
 * Governance is inherited, not re-implemented: a tool call runs the published version through the same path as the
 * REST API (validation, workspace policy, concurrency and budget limits, idempotency, run record, audit).
 *
 * This module is pure (no I/O): the route injects a `McpBackend`. Spec: modelcontextprotocol.io (2025-06-18). */

export const SUPPORTED_PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"] as const;
export const LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0];
export const SERVER_INFO = { name: "skills-factory", title: "Skills Factory", version: "1.0.0" };

export interface CatalogInput { name: string; type: string; required: boolean; from?: string; default?: string | null; schema?: unknown }
export interface CatalogSkill { slug: string; name: string; purpose?: string | null; version: number; repo_skill: string | null; inputs: CatalogInput[] }
export interface LibraryInfo { id: string; card: string; stage: string | null; modes: Partial<Record<"new" | "existing", { bring: string }>> }

export interface McpScope { kind: "workspace" | "role" | "team" | "stage"; slug: string | null; title: string; skills: Set<string> | null /* library ids; null = all */ }

export interface RunReply { http: number; body: Record<string, unknown> }
export interface McpBackend {
  scope: McpScope;
  catalog(): Promise<CatalogSkill[]>;
  library(id: string): LibraryInfo | null;
  route(task: string, k: number): { skill: string; score: number }[];
  run(slug: string, args: { inputs: Record<string, unknown>; assumptions?: Record<string, string> }, idempotencyKey: string | null): Promise<RunReply>;
  getRun(runId: string): Promise<RunReply>;
}

type Json = Record<string, unknown>;
export interface JsonRpcRequest { jsonrpc: "2.0"; id?: string | number | null; method: string; params?: Json }
export type JsonRpcResponse = { jsonrpc: "2.0"; id: string | number | null } & ({ result: unknown } | { error: { code: number; message: string; data?: unknown } });

export const RPC = { PARSE: -32700, INVALID_REQUEST: -32600, METHOD_NOT_FOUND: -32601, INVALID_PARAMS: -32602, INTERNAL: -32603 } as const;
const ok = (id: JsonRpcRequest["id"], result: unknown): JsonRpcResponse => ({ jsonrpc: "2.0", id: id ?? null, result });
const fail = (id: JsonRpcRequest["id"], code: number, message: string, data?: unknown): JsonRpcResponse =>
  ({ jsonrpc: "2.0", id: id ?? null, error: { code, message, ...(data !== undefined ? { data } : {}) } });

/** A secondary find_skill hit must score at least this share of the best hit. */
export const RELEVANCE_FLOOR = 0.5;

const TEXT_TYPES = new Set(["csv", "json", "md", "txt", "file", "sql"]);
const TOOL_NAME = /^[a-zA-Z0-9_-]{1,64}$/;
const RESERVED = new Set(["find_skill", "get_run"]);

/** JSON Schema for one skill's inputs, from its published contract. */
export function inputSchema(inputs: CatalogInput[]): Json {
  const properties: Json = {};
  const required: string[] = [];
  for (const i of inputs) {
    if (i.type === "path") continue;                                  // output targets: the runtime chooses them
    const about = (i.from || i.name.replace(/_/g, " ")).trim();
    let p: Json;
    if (i.type === "dir") p = { type: "object", additionalProperties: { type: "string" },
      description: `${about}. A folder: an object mapping each relative file path to its text content, e.g. {"0001_init.sql": "create table …"}.` };
    else if (i.type === "flag") p = { type: "boolean", description: about };
    else if (TEXT_TYPES.has(i.type)) p = { type: "string", description: `${about}. The file's full text content (${i.type === "file" ? "text" : i.type.toUpperCase()}).` };
    else p = { type: "string", description: about };
    if (i.default != null) p.default = i.default;
    properties[i.name] = p;
    if (i.required && i.default == null) required.push(i.name);
  }
  return { type: "object", properties, ...(required.length ? { required } : {}), additionalProperties: false };
}

/** The skills of the catalog that are in scope (scope.skills holds library ids; workspace skills map via repo_skill). */
export function inScope(catalog: CatalogSkill[], scope: McpScope): CatalogSkill[] {
  return catalog.filter((s) => TOOL_NAME.test(s.slug) && !RESERVED.has(s.slug) && (!scope.skills || (s.repo_skill !== null && scope.skills.has(s.repo_skill))));
}

function toolFor(s: CatalogSkill, lib: LibraryInfo | null): Json {
  const lines = [lib?.card || s.purpose || s.name];
  if (lib?.modes.new) lines.push(`Starting new — bring: ${lib.modes.new.bring}.`);
  if (lib?.modes.existing) lines.push(`Improving what exists — bring: ${lib.modes.existing.bring}.`);
  lines.push(`Runs the published version ${s.version} on the Skills Factory runtime; every output is checked and the run is recorded. Returns the result and a run_id.`);
  return {
    name: s.slug, title: s.name, description: lines.join("\n"), inputSchema: inputSchema(s.inputs),
    annotations: { title: s.name, readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  };
}

const FIND_SKILL = {
  name: "find_skill", title: "Find the right skill",
  description: "Describe a task in plain words; returns the best-matching skills with what each produces, its lifecycle stage, and which tool here runs it.",
  inputSchema: { type: "object", properties: { task: { type: "string", description: "The work to be done, in a sentence." } }, required: ["task"], additionalProperties: false },
  annotations: { readOnlyHint: true, openWorldHint: false },
};
const GET_RUN = {
  name: "get_run", title: "Get a run",
  description: "Status and outputs of an earlier run (use the run_id a skill returned, e.g. when it was still running).",
  inputSchema: { type: "object", properties: { run_id: { type: "string" } }, required: ["run_id"], additionalProperties: false },
  annotations: { readOnlyHint: true, openWorldHint: false },
};

/** Human-readable result of a run, primary report first. */
export function renderRun(body: Json): string {
  const status = String(body.status ?? "unknown");
  const checks = Array.isArray(body.checks) ? (body.checks as { pass?: boolean }[]) : [];
  const passed = checks.filter((c) => c.pass).length;
  const outputs = Array.isArray(body.outputs) ? (body.outputs as { path: string; content_text?: string | null }[]) : [];
  const head = [`Run ${body.run_id ?? "?"} — ${status}${checks.length ? ` · ${passed}/${checks.length} checks passed` : ""}`];
  if (body.error) head.push(`Note: ${String(body.error)}`);
  const primary = outputs.find((o) => /\.md$/.test(o.path) && o.content_text) ?? outputs.find((o) => o.content_text);
  const rest = outputs.filter((o) => o !== primary).map((o) => o.path);
  const parts = [head.join("\n")];
  if (primary?.content_text) parts.push(`--- ${primary.path} ---\n${primary.content_text.slice(0, 60_000)}`);
  if (rest.length) parts.push(`Other outputs: ${rest.join(", ")} (full contents in structuredContent.outputs).`);
  return parts.join("\n\n");
}

export async function handle(msg: unknown, be: McpBackend): Promise<JsonRpcResponse | null> {
  if (!msg || typeof msg !== "object" || Array.isArray(msg)) return fail(null, RPC.INVALID_REQUEST, "expected a JSON-RPC 2.0 object");
  const m = msg as JsonRpcRequest;
  if (m.jsonrpc !== "2.0" || typeof m.method !== "string") return fail(m.id ?? null, RPC.INVALID_REQUEST, "expected jsonrpc \"2.0\" and a method");
  const isNotification = !("id" in m) || m.id === undefined;
  if (isNotification) return null;                                      // notifications/initialized, cancelled, …: 202, no body
  const params = (m.params && typeof m.params === "object" ? m.params : {}) as Json;
  try {
    switch (m.method) {
      case "initialize": {
        const asked = String(params.protocolVersion ?? "");
        const version = (SUPPORTED_PROTOCOL_VERSIONS as readonly string[]).includes(asked) ? asked : LATEST_PROTOCOL_VERSION;
        return ok(m.id, {
          protocolVersion: version, capabilities: { tools: { listChanged: false } }, serverInfo: SERVER_INFO,
          instructions: `Skills Factory — ${be.scope.title}. Each tool is a published, tested skill that runs on the factory runtime and returns checked outputs. `
            + "Call find_skill with a plain-language task when unsure which tool fits. File inputs take the file's text; folder inputs take {relative path: content}.",
        });
      }
      case "ping": return ok(m.id, {});
      case "tools/list": {
        const tools = inScope(await be.catalog(), be.scope).map((s) => toolFor(s, s.repo_skill ? be.library(s.repo_skill) : null));
        return ok(m.id, { tools: [...tools, FIND_SKILL, GET_RUN] });
      }
      case "tools/call": {
        const name = String(params.name ?? "");
        const args = (params.arguments && typeof params.arguments === "object" && !Array.isArray(params.arguments) ? params.arguments : {}) as Json;
        if (name === "find_skill") return ok(m.id, await findSkill(args, be));
        if (name === "get_run") {
          if (typeof args.run_id !== "string" || !args.run_id) return fail(m.id, RPC.INVALID_PARAMS, "run_id is required");
          const r = await be.getRun(args.run_id);
          return ok(m.id, r.http >= 400 ? toolError(r.body) : { content: [{ type: "text", text: renderRun(r.body) }], structuredContent: r.body });
        }
        const skill = inScope(await be.catalog(), be.scope).find((s) => s.slug === name);
        if (!skill) return fail(m.id, RPC.INVALID_PARAMS, `unknown tool: ${name}`);
        const r = await be.run(skill.slug, { inputs: args }, null);
        if (r.http >= 400) return ok(m.id, toolError(r.body));
        return ok(m.id, { content: [{ type: "text", text: renderRun(r.body) }], structuredContent: r.body, isError: runProducedNothing(r.body) });
      }
      default: return fail(m.id, RPC.METHOD_NOT_FOUND, `method not found: ${m.method}`);
    }
  } catch (e) {
    return fail(m.id, RPC.INTERNAL, e instanceof Error ? e.message : String(e));
  }
}

/** A run that failed AND produced no output is a tool error; a run whose checks flagged problems in its outputs
 *  (e.g. a lint gate that found RLS gaps) is a successful tool call reporting a negative verdict. */
export const runProducedNothing = (b: Json) =>
  ["failed", "timeout", "cancelled"].includes(String(b.status)) && !(Array.isArray(b.outputs) && b.outputs.length > 0);

/** API errors (missing inputs, budget, not published) are tool-level errors the model can act on — not protocol errors. */
function toolError(body: Json) {
  const e = (body.error ?? {}) as { code?: string; message?: string; details?: unknown };
  const details = e.details ? `\n${JSON.stringify(e.details)}` : "";
  return { content: [{ type: "text", text: `${e.code ?? "error"}: ${e.message ?? "the run was rejected"}${details}` }], isError: true };
}

async function findSkill(args: Json, be: McpBackend) {
  const task = typeof args.task === "string" ? args.task.trim() : "";
  if (task.length < 4) return { content: [{ type: "text", text: "Describe the task in a sentence." }], isError: true };
  const here = new Map(inScope(await be.catalog(), be.scope).filter((s) => s.repo_skill).map((s) => [s.repo_skill as string, s.slug]));
  // only real matches: drop hits far weaker than the best one (BM25 always returns k results, relevant or not)
  const ranked = be.route(task, 5);
  const top = ranked[0]?.score ?? 0;
  const hits = ranked.filter((h, i) => i === 0 || h.score >= top * RELEVANCE_FLOOR).map((h) => {
    const lib = be.library(h.skill);
    return { skill: h.skill, produces: lib?.card ?? "", stage: lib?.stage ?? null, tool: here.get(h.skill) ?? null,
      starting_points: Object.fromEntries(Object.entries(lib?.modes ?? {}).map(([k, v]) => [k, v?.bring])) };
  });
  const lines = hits.map((h, i) => `${i + 1}. ${h.skill} — ${h.produces}${h.tool ? ` → call tool "${h.tool}"` : " (not published on this server; ask a workspace admin to publish it)"}`);
  return { content: [{ type: "text", text: lines.length ? lines.join("\n") : "No skill matches; try different words." }], structuredContent: { hits } };
}
