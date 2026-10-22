// Pipeline composition (docs/DELIVERY-PIPELINES.md → When no template fits): lib/delivery/compose.ts is a port of
// scripts/compose_pipeline.py. Parity: every fixture under tests/fixtures/compose/ was produced by the Python script
// (--bundle); re-composing its `input` here must give the same pipeline, decisions and notes. Catalog data comes from
// data/ (ingest): request-kinds.json, role-templates.json, skills.json (metadata.fits).
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { compose, explain, fitsMatch, resolveKind, stacksFromProfile, ComposeError, type ComposeCatalog, type RequestKinds, type SkillFits } from "../lib/delivery/compose.ts";
import { handle, renderCompose, type McpBackend } from "../lib/factory/mcp.ts";

const FIX = "tests/fixtures/compose";
const KINDS = JSON.parse(readFileSync("data/request-kinds.json", "utf8")) as RequestKinds;
const ROLES = JSON.parse(readFileSync("data/role-templates.json", "utf8")) as { name: string; stages?: string[]; skills?: string[] }[];
const SKILLS = JSON.parse(readFileSync("data/skills.json", "utf8")) as { id: string; metadata?: { fits?: SkillFits } }[];
const CATALOG: ComposeCatalog = { roles: ROLES.map((r) => ({ name: r.name, stages: r.stages ?? [], skills: r.skills ?? [] })), fits: Object.fromEntries(SKILLS.map((s) => [s.id, s.metadata?.fits ?? null])) };
type Bundle = { input: { stacks: string[]; request_kind: string; mode: "brownfield" | "greenfield" | null; stages: string[] | null; name: string | null }; pipeline: Record<string, unknown> | null; decisions: unknown[]; notes: string[] };
const bundles = existsSync(FIX) ? readdirSync(FIX).filter((f) => f.endsWith(".json")).sort().map((f) => [f, JSON.parse(readFileSync(`${FIX}/${f}`, "utf8")) as Bundle] as const) : [];

test("the catalog the portal ships carries fits for every build skill and the roles' stages", () => {
  assert.ok(bundles.length >= 5, "parity fixtures exist (see tests/fixtures/compose/README.md)");
  const build = SKILLS.filter((s) => s.id.startsWith("build/"));
  assert.ok(build.length >= 15);
  for (const s of build) assert.ok(s.metadata?.fits?.stacks?.length && s.metadata.fits.request_kinds?.length, `${s.id} declares fits`);
  for (const st of ["requirements", "architecture", "build", "evaluate", "deploy", "operate"]) assert.ok(CATALOG.roles.some((r) => r.stages?.includes(st)), `a role owns ${st}`);
  assert.deepEqual(KINDS.kinds.filter((k) => !k.alias_of).map((k) => k.id), ["feature", "fix", "hardening", "migration", "greenfield"]);
});

for (const [file, b] of bundles) {
  test(`parity with the Python composer: ${file}`, () => {
    const r = compose({ stacks: b.input.stacks, requestKind: b.input.request_kind, mode: b.input.mode, stages: b.input.stages, name: b.input.name }, CATALOG, KINDS);
    assert.deepEqual(r.pipeline, b.pipeline);
    assert.deepEqual(r.decisions, b.decisions);
    assert.deepEqual(r.notes, b.notes);
  });
}

test("the JS/AWS feature composition is the feature-delivery template, stage for stage", () => {
  const b = bundles.find(([f]) => f === "feature-js-aws.json")![1];
  const shipped = JSON.parse(readFileSync("data/pipelines.json", "utf8")) as { name: string; stages: { id: string; role: string; steps: { id: string; kind: string; skill?: string }[] }[] }[];
  const tpl = shipped.find((p) => p.name === "feature-delivery")!;
  const stages = (b.pipeline as { stages: { id: string; role: string; steps: { id: string; kind: string; skill?: string }[] }[] }).stages;
  assert.deepEqual(stages.map((s) => [s.id, s.role, s.steps.map((t) => [t.id, t.kind, t.skill ?? null])]), tpl.stages.map((s) => [s.id, s.role, s.steps.map((t) => [t.id, t.kind, t.skill ?? null])]));
});

test("a stack with no fitting build skills drops stages with notes and never wires an unfit skill", () => {
  const r = compose({ stacks: ["python", "tests"], requestKind: "feature" }, CATALOG, KINDS);
  assert.deepEqual(r.pipeline!.stages.map((s) => s.id), ["requirements", "architecture", "operate"]);
  assert.deepEqual(r.notes.map((n) => n.split(":")[0]), ["stage build dropped", "stage evaluate dropped", "stage deploy dropped"]);
  for (const s of r.pipeline!.stages) for (const t of s.steps) if (t.skill) assert.equal(fitsMatch(CATALOG.fits[t.skill], ["python", "tests"], "feature"), null, t.skill);
  assert.ok(r.decisions.some((d) => d.skill === "build/nextjs-enterprise-conventions" && d.decision === "rejected" && /stack: fits nextjs/.test(d.why)));
  assert.match(explain(r), /note: stage build dropped/);
});

test("deterministic and pure: the same input composes the same pipeline; no input is mutated", () => {
  const input = { stacks: ["react", "nextjs"], requestKind: "fix" as const };
  const a = compose(input, CATALOG, KINDS), c = compose(input, CATALOG, KINDS);
  assert.deepEqual(a, c);
  assert.deepEqual(input.stacks, ["react", "nextjs"]);
  assert.deepEqual(a.pipeline!.fits.stacks, ["nextjs", "react"]);
  assert.equal(a.pipeline!.name, "composed-fix-nextjs-react");
  const build = a.pipeline!.stages[0];
  assert.deepEqual(build.steps.map((s) => s.id), ["brief", "spec", "files", "code", "conventions"]);
  assert.deepEqual((build.steps[2] as { inputs: unknown; produces: unknown }).produces, ["files.txt"]);   // no tasks.csv in a fix: the builder names the files
  assert.deepEqual((build.steps[2] as { inputs: unknown }).inputs, { plan: "$steps.spec:spec.md", target: "$repo" });
  assert.deepEqual((build.steps[3] as { inputs: unknown }).inputs, { plan: "$steps.spec:spec.md", files: "$steps.files:files.txt", target: "$repo" });
});

test("unknown kind, mode and stage are clear errors; new-app is an alias of greenfield", () => {
  assert.throws(() => compose({ stacks: ["nextjs"], requestKind: "refactor" }, CATALOG, KINDS), (e: unknown) => e instanceof ComposeError && /unknown request kind 'refactor' \(one of feature, fix, greenfield, hardening, migration, new-app\)/.test((e as Error).message));
  assert.throws(() => compose({ stacks: ["nextjs"], requestKind: "feature", stages: ["build", "shipping"] }, CATALOG, KINDS), /unknown stage\(s\) \['shipping'\]/);
  assert.equal(resolveKind(KINDS, "new-app").id, "greenfield");
  const gf = compose({ stacks: ["nextjs"], requestKind: "new-app" }, CATALOG, KINDS).pipeline!;
  assert.equal(gf.mode, "greenfield"); assert.equal(gf.stack_profile.after, "bootstrap"); assert.equal(gf.stages[0].id, "bootstrap");
  assert.deepEqual(gf.inputs.map((i) => i.name), ["repo", "name", "request", "brief"]);
});

test("stacksFromProfile mirrors the Python mapping", () => {
  assert.deepEqual(stacksFromProfile({ flavour: "js", framework: "nextjs", deploy_target: "aws", test_runner: "vitest", e2e: "playwright", migrations_dir: null, evidence: { deploy_target: ".github/workflows/aws-deploy-production.yml" } }), ["github-actions", "nextjs", "react", "tests"]);
  assert.deepEqual(stacksFromProfile({ flavour: "ts", framework: "nextjs", deploy_target: "vercel", test_runner: "jest", e2e: "none", migrations_dir: "supabase/migrations", evidence: { deploy_target: ".vercel/project.json" } }), ["nextjs", "react", "supabase", "tests", "typescript", "vercel"]);
  assert.deepEqual(stacksFromProfile({ flavour: "python", framework: "fastapi", test_runner: "pytest" }), ["python", "tests"]);
  assert.deepEqual(stacksFromProfile({}), []);
});

// ───────── MCP `compose` tool: schema, argument checks, rendering; the backend is in-memory ─────────
function backend(calls: unknown[] = []): McpBackend {
  const r = compose({ stacks: ["nextjs", "react"], requestKind: "fix" }, CATALOG, KINDS);
  return {
    scope: { kind: "workspace", slug: null, title: "workspace", skills: null },
    catalog: async () => [], library: () => null, route: () => [],
    run: async () => ({ http: 200, body: {} }), getRun: async () => ({ http: 200, body: {} }),
    pipelines: () => [], deliver: async () => ({ http: 201, body: {} }), deliveryStatus: async () => ({ http: 404, body: { error: { code: "not_found", message: "no" } } }),
    requestKinds: () => KINDS.kinds.filter((k) => !k.alias_of).map((k) => ({ id: k.id, description: k.description })),
    compose: async (a) => { calls.push(a); return a.repo === "acme/none" ? { http: 404, body: { error: { code: "not_found", message: "acme/none is not in this workspace's catalog" } } }
      : { http: 200, body: { pipeline: r.pipeline, decisions: r.decisions, notes: r.notes, stacks: ["nextjs", "react"] } as unknown as Record<string, unknown> }; },
  };
}
const rpc = (method: string, params?: object, id = 1) => ({ jsonrpc: "2.0", id, method, ...(params ? { params } : {}) });

test("tools/list advertises compose with the request kinds; tools/call composes and renders the decision table", async () => {
  const list = await handle(rpc("tools/list"), backend()) as { result: { tools: { name: string; inputSchema: { required: string[]; properties: { request_kind: { enum: string[] } } } }[] } };
  const tool = list.result.tools.find((t) => t.name === "compose")!;
  assert.deepEqual(tool.inputSchema.required, ["request_kind"]);
  assert.deepEqual(tool.inputSchema.properties.request_kind.enum, ["feature", "fix", "hardening", "migration", "greenfield"]);
  const calls: unknown[] = [];
  const r = await handle(rpc("tools/call", { name: "compose", arguments: { repo: "acme/billing", request_kind: "fix" } }), backend(calls)) as { result: { isError?: boolean; content: { text: string }[]; structuredContent: { pipeline: { name: string }; decisions: unknown[] } } };
  assert.deepEqual(calls, [{ repo: "acme/billing", request_kind: "fix", mode: undefined, stack_profile: undefined }]);
  assert.equal(r.result.isError, false);
  assert.equal(r.result.structuredContent.pipeline.name, "composed-fix-nextjs-react");
  assert.match(r.result.content[0].text, /Composed pipeline composed-fix-nextjs-react — 4 stage\(s\)\n- build \(full-stack-engineer\): brief \[compose\] → spec \[compose\] → files \[agent\] → code \[agent\] → build\/nextjs-enterprise-conventions/);
  assert.match(r.result.content[0].text, /Decisions:\n(- build · [^\n]*\n)*- build · tests · build\/test-strategy-tdd: rejected — needs step\(s\) feature/);
  const missing = await handle(rpc("tools/call", { name: "compose", arguments: { request_kind: "fix" } }), backend()) as { error: { message: string } };
  assert.match(missing.error.message, /repo or stack_profile is required/);
  const unknown = await handle(rpc("tools/call", { name: "compose", arguments: { repo: "a/b", request_kind: "nope" } }), backend()) as { error: { message: string } };
  assert.match(unknown.error.message, /unknown request_kind: nope \(one of feature, fix, hardening, migration, greenfield\)/);
  const gone = await handle(rpc("tools/call", { name: "compose", arguments: { repo: "acme/none", request_kind: "fix" } }), backend()) as { result: { isError: boolean; content: { text: string }[] } };
  assert.equal(gone.result.isError, true); assert.match(gone.result.content[0].text, /not_found/);
  assert.match(renderCompose({ pipeline: null, decisions: [], notes: ["nothing composed: no stage kept a fitting skill"] }), /Nothing composed\.\n\nNote: nothing composed/);
});
