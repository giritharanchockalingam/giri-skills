// MCP protocol core: unit tests against an in-memory backend (the HTTP route and live runtime are exercised in CI/e2e).
import { test } from "node:test";
import assert from "node:assert/strict";
import { handle, inputSchema, inScope, renderRun, RPC, LATEST_PROTOCOL_VERSION, type McpBackend, type CatalogSkill } from "../lib/factory/mcp.ts";

const CATALOG: CatalogSkill[] = [
  { slug: "supabase-schema-rls", name: "Supabase schema RLS", version: 2, repo_skill: "build/supabase-schema-rls",
    inputs: [{ name: "migrations", type: "dir", required: true, from: "migrations folder" }, { name: "out_dir", type: "path", required: false }] },
  { slug: "effort-estimator", name: "Effort estimator", version: 1, repo_skill: "presales/effort-estimator",
    inputs: [{ name: "wbs", type: "csv", required: true }, { name: "client", type: "string", required: true }, { name: "iterations", type: "string", required: false, default: "10000" }] },
  { slug: "my-authored", name: "Authored", version: 1, repo_skill: null, inputs: [] },
];
function backend(skills: Set<string> | null = null, calls: unknown[] = []): McpBackend {
  return {
    scope: { kind: skills ? "role" : "workspace", slug: skills ? "dev" : null, title: skills ? "role Developer" : "workspace", skills },
    catalog: async () => CATALOG,
    library: (id) => ({ id, card: `card of ${id}`, stage: "build", modes: { existing: { bring: "your migrations folder" } } }),
    route: () => [{ skill: "build/supabase-schema-rls", score: 3 }, { skill: "build/security-review", score: 2 }],
    run: async (slug, args) => { calls.push({ slug, args }); return slug === "effort-estimator"
      ? { http: 400, body: { error: { code: "missing_inputs", message: "Required input(s) missing: wbs.", details: { missing: ["wbs"] } } } }
      : { http: 200, body: { run_id: "r1", status: "failed", checks: [{ pass: true }, { pass: false }], outputs: [{ path: "rls-lint.txt", content_text: "ERROR RLS001 table public.notes" }] } }; },
    getRun: async (id) => ({ http: 200, body: { run_id: id, status: "succeeded", checks: [], outputs: [] } }),
  };
}
const rpc = (method: string, params?: object, id: number | null = 1) => ({ jsonrpc: "2.0", ...(id !== null ? { id } : {}), method, ...(params ? { params } : {}) });

test("initialize negotiates the protocol version and advertises tools", async () => {
  const r = await handle(rpc("initialize", { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "t", version: "0" } }), backend()) as { result: { protocolVersion: string; capabilities: object; serverInfo: { name: string } } };
  assert.equal(r.result.protocolVersion, "2025-03-26");
  assert.deepEqual(r.result.capabilities, { tools: { listChanged: false } });
  assert.equal(r.result.serverInfo.name, "skills-factory");
  const r2 = await handle(rpc("initialize", { protocolVersion: "1999-01-01" }), backend()) as { result: { protocolVersion: string } };
  assert.equal(r2.result.protocolVersion, LATEST_PROTOCOL_VERSION);
});

test("notifications get no response; bad messages and unknown methods get JSON-RPC errors", async () => {
  assert.equal(await handle(rpc("notifications/initialized", undefined, null), backend()), null);
  assert.equal(((await handle([1], backend())) as { error: { code: number } }).error.code, RPC.INVALID_REQUEST);
  assert.equal(((await handle({ id: 1, method: "x" }, backend())) as { error: { code: number } }).error.code, RPC.INVALID_REQUEST);
  assert.equal(((await handle(rpc("resources/list"), backend())) as { error: { code: number } }).error.code, RPC.METHOD_NOT_FOUND);
  assert.deepEqual(((await handle(rpc("ping"), backend())) as { result: object }).result, {});
});

test("tools/list: one tool per published skill in scope, plus find_skill and get_run", async () => {
  const all = ((await handle(rpc("tools/list"), backend())) as { result: { tools: { name: string; inputSchema: { required?: string[]; properties: Record<string, { type: string }> }; description: string }[] } }).result.tools;
  assert.deepEqual(all.map((t) => t.name), ["supabase-schema-rls", "effort-estimator", "my-authored", "find_skill", "get_run"]);
  const rls = all[0];
  assert.equal(rls.inputSchema.properties.migrations.type, "object");          // a folder
  assert.ok(!("out_dir" in rls.inputSchema.properties));                       // path inputs are runtime-owned
  assert.match(rls.description, /Improving what exists — bring: your migrations folder/);
  const est = all[1];
  assert.deepEqual(est.inputSchema.required, ["wbs", "client"]);               // defaults are not required
  const role = ((await handle(rpc("tools/list"), backend(new Set(["build/supabase-schema-rls"])))) as { result: { tools: { name: string }[] } }).result.tools;
  assert.deepEqual(role.map((t) => t.name), ["supabase-schema-rls", "find_skill", "get_run"]);   // scoped: authored + other skills hidden
});

test("tools/call runs the published skill; a negative verdict with outputs is not a tool error", async () => {
  const calls: unknown[] = [];
  const r = await handle(rpc("tools/call", { name: "supabase-schema-rls", arguments: { migrations: { "0001.sql": "create table x();" } } }), backend(null, calls)) as { result: { isError: boolean; content: { text: string }[]; structuredContent: { run_id: string } } };
  assert.deepEqual(calls, [{ slug: "supabase-schema-rls", args: { inputs: { migrations: { "0001.sql": "create table x();" } } } }]);
  assert.equal(r.result.isError, false);
  assert.match(r.result.content[0].text, /Run r1 — failed · 1\/2 checks passed/);
  assert.match(r.result.content[0].text, /ERROR RLS001/);
  assert.equal(r.result.structuredContent.run_id, "r1");
});

test("tools/call: API rejection is a tool error the model can fix; unknown or out-of-scope tool is invalid params", async () => {
  const r = await handle(rpc("tools/call", { name: "effort-estimator", arguments: {} }), backend()) as { result: { isError: boolean; content: { text: string }[] } };
  assert.equal(r.result.isError, true);
  assert.match(r.result.content[0].text, /missing_inputs: Required input\(s\) missing: wbs/);
  const scoped = await handle(rpc("tools/call", { name: "effort-estimator", arguments: {} }), backend(new Set(["build/supabase-schema-rls"]))) as { error: { code: number } };
  assert.equal(scoped.error.code, RPC.INVALID_PARAMS);
});

test("find_skill routes a task and says which tool runs it here", async () => {
  const r = await handle(rpc("tools/call", { name: "find_skill", arguments: { task: "check my RLS policies" } }), backend()) as { result: { content: { text: string }[]; structuredContent: { hits: { skill: string; tool: string | null }[] } } };
  assert.deepEqual(r.result.structuredContent.hits.map((h) => h.tool), ["supabase-schema-rls", null]);
  assert.match(r.result.content[0].text, /not published on this server/);
});

test("find_skill drops weak secondary matches", async () => {
  const be = { ...backend(), route: () => [{ skill: "build/supabase-schema-rls", score: 10 }, { skill: "build/security-review", score: 6 }, { skill: "x/filler", score: 2 }] };
  const r = await handle(rpc("tools/call", { name: "find_skill", arguments: { task: "check my RLS" } }), be) as { result: { structuredContent: { hits: { skill: string }[] } } };
  assert.deepEqual(r.result.structuredContent.hits.map((h) => h.skill), ["build/supabase-schema-rls", "build/security-review"]);
});

test("helpers: schema, scope and rendering", () => {
  assert.deepEqual(inputSchema([{ name: "strict", type: "flag", required: false }]), { type: "object", properties: { strict: { type: "boolean", description: "strict" } }, additionalProperties: false });
  assert.equal(inScope([{ ...CATALOG[0], slug: "find_skill" }], { kind: "workspace", slug: null, title: "", skills: null }).length, 0);   // reserved names never shadowed
  assert.match(renderRun({ run_id: "x", status: "succeeded", outputs: [{ path: "a.md", content_text: "# A" }, { path: "b.json", content_text: "{}" }] }), /--- a\.md ---\n# A[\s\S]*Other outputs: b\.json/);
});

test("job roles: a skill the key may not run is not a tool, cannot be called, and find_skill says why", async () => {
  const restricted = CATALOG.map((s) => (s.slug === "supabase-schema-rls" ? { ...s, allowed: false } : s));
  const be = { ...backend(), catalog: async () => restricted };
  const list = await handle(rpc("tools/list"), be) as { result: { tools: { name: string }[] } };
  assert.ok(!list.result.tools.some((t) => t.name === "supabase-schema-rls"));
  assert.ok(list.result.tools.some((t) => t.name === "effort-estimator"));
  const call = await handle(rpc("tools/call", { name: "supabase-schema-rls", arguments: {} }), be) as { error: { code: number } };
  assert.equal(call.error.code, RPC.INVALID_PARAMS);
  const find = await handle(rpc("tools/call", { name: "find_skill", arguments: { task: "check row level security in my migrations" } }), be) as { result: { content: { text: string }[]; structuredContent: { hits: { skill: string; tool: string | null; access?: string }[] } } };
  const hit = find.result.structuredContent.hits.find((h) => h.skill === "build/supabase-schema-rls")!;
  assert.equal(hit.tool, null);
  assert.equal(hit.access, "not_in_role");
  assert.match(find.result.content[0].text, /not in this key's job roles/);
});
