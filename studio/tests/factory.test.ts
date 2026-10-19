// Unit tests for the factory's pure contracts. Run: npm run test:unit  (node --experimental-strip-types --test)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { validateManifest, canonicalJson, emptyManifest, type Manifest } from "../lib/factory/manifest.ts";
import { validateInputs, validateJson, validateOutputContract, describeInputs } from "../lib/factory/schema.ts";
import { manifestHash, sha256, generateApiKey, looksLikeApiKey, apiKeyHash, secretsEqual } from "../lib/factory/hash.ts";
import { evalGate, approvalGate, nextAction, type ReleaseStateRow } from "../lib/factory/release.ts";
import { can } from "../lib/factory/roles.ts";
import { manifestFromRepoSkill, casesFromRepoSkill, type RepoSkill } from "../lib/factory/import.ts";

const good = (): Manifest => ({
  ...emptyManifest(),
  purpose: "Validate an invoice against a purchase order",
  inputs: [{ name: "invoice", type: "json", required: true, from: "AP system export", default: null, flag: null, schema: { type: "object", required: ["total"], properties: { total: { type: "number", minimum: 0 } } } },
           { name: "po", type: "csv", required: false, from: "", default: null, flag: null, schema: null }],
  outputs: [{ path: "{out}/result.json", checks: ["exists", "json"], schema: { type: "object", required: ["status"], properties: { status: { type: "string", enum: ["match", "mismatch"] } } } }],
  run: [{ step: "check", kind: "script", cmd: "python3 scripts/check.py {invoice} [--po {po}]", stdout: "{out}/result.json" }],
  allowed_tools: ["script"],
});

test("manifest: a valid manifest normalises and hashes deterministically", () => {
  const v = validateManifest(good());
  assert.equal(v.ok, true);
  if (!v.ok) return;
  const h1 = manifestHash(v.manifest);
  const reordered = Object.fromEntries(Object.entries(v.manifest).reverse().map(([k, val]) => [k, val && typeof val === "object" && !Array.isArray(val) ? Object.fromEntries(Object.entries(val).reverse()) : val]));
  assert.equal(manifestHash(reordered), h1, "key order must not change the hash");
  assert.match(h1, /^[0-9a-f]{64}$/);
  const changed = { ...v.manifest, limits: { ...v.manifest.limits, timeout_s: 10 } };
  assert.notEqual(manifestHash(changed), h1, "any content change changes the hash");
  assert.equal(canonicalJson({ b: 1, a: [3, { z: 1, y: undefined }] }), '{"a":[3,{"z":1}],"b":1}');
});

test("manifest: problems are reported with paths", () => {
  const m = good();
  m.inputs.push({ name: "invoice", type: "json", required: true, from: "", default: null, flag: null, schema: null }); // duplicate
  m.outputs = [];
  m.limits.timeout_s = 900;
  m.run.push({ step: "memo", kind: "llm", template: "assets/t.md", out: "{out}/memo.md" }); // llm not allowed + provider none
  const v = validateManifest(m);
  assert.equal(v.ok, false);
  if (v.ok) return;
  const paths = v.problems.map((p) => p.path);
  assert.ok(paths.includes("inputs[2].name"), "duplicate input");
  assert.ok(paths.includes("outputs"), "no outputs");
  assert.ok(paths.includes("limits.timeout_s"), "timeout ceiling");
  assert.ok(paths.includes("run"), "tool not allowed");
  assert.ok(paths.includes("model_config.provider"), "llm steps need a provider");
  assert.equal(validateManifest("nope").ok, false);
});

test("inputs: required, unknown, json schema, csv header, flags, dir rejected", () => {
  const m = good();
  let r = validateInputs(m, {});
  assert.deepEqual(r.missing, ["invoice"]);
  r = validateInputs(m, { invoice: { total: 5 }, extra: 1 });
  assert.equal(r.missing.length, 0);
  assert.equal(r.problems[0].path, "inputs.extra");
  assert.equal(r.inputs.invoice.kind, "text");
  r = validateInputs(m, { invoice: '{"total": -1}' });
  assert.match(r.problems[0].message, /minimum|>= 0/);
  r = validateInputs(m, { invoice: "{not json" });
  assert.match(r.problems[0].message, /not valid JSON/);
  r = validateInputs(m, { invoice: { total: 1 }, po: "no-commas-here" });
  assert.match(r.problems[0].message, /CSV needs a header/);
  r = validateInputs(m, { invoice: { total: 1 }, po: "sku,qty\nA,1" });
  assert.equal(r.problems.length, 0);
  const m2 = { inputs: [{ name: "d", type: "dir" as const, required: true, from: "", default: null, flag: null, schema: null }, { name: "f", type: "flag" as const, required: false, from: "", default: null, flag: "--x", schema: null }] };
  r = validateInputs(m2, { d: "/tmp", f: true });
  assert.match(r.problems[0].message, /directory inputs/);
  assert.deepEqual(r.inputs.f, { kind: "value", value: "true" });
  // fixtures only from eval cases
  r = validateInputs(m, { invoice: { kind: "fixture", path: "evals/fixtures/x.json" } });
  assert.match(r.problems[0].message, /evaluation cases/);
  r = validateInputs(m, { invoice: { kind: "fixture", path: "evals/fixtures/x.json" } }, { allowFixtures: true });
  assert.equal(r.problems.length, 0);
  r = validateInputs(m, { invoice: { kind: "fixture", path: "../../etc/passwd" } }, { allowFixtures: true });
  assert.equal(r.problems.length, 1);
  const refs = describeInputs({ invoice: { kind: "text", content: "{}" }, n: { kind: "value", value: "Acme" } }, sha256);
  assert.equal(refs[0].sha256, sha256("{}"));
  assert.equal(refs[1].value, "Acme");
});

test("json schema subset", () => {
  const s = { type: "object" as const, required: ["a"], properties: { a: { type: "integer" as const, maximum: 3 }, b: { type: "array" as const, items: { type: "string" as const, pattern: "^x" } } }, additionalProperties: false };
  assert.equal(validateJson(s, { a: 1, b: ["xy"] }).length, 0);
  const p = validateJson(s, { a: 4.5, b: ["y"], c: 1 });
  assert.deepEqual(p.map((x) => x.path).sort(), ["$.a", "$.b[0]", "$.c"]);
  assert.equal(validateJson({ type: "number" }, 2).length, 0, "integer satisfies number");
  assert.equal(validateJson({ enum: [1, "a"] }, "b").length, 1);
});

test("output contract: missing and schema-invalid outputs fail", () => {
  const m = good();
  let r = validateOutputContract(m, []);
  assert.equal(r.ok, false);
  assert.match(r.problems[0].message, /not produced/);
  r = validateOutputContract(m, [{ path: "result.json", bytes: 10, sha256: "x", content_text: '{"status":"maybe"}' }]);
  assert.equal(r.ok, false);
  assert.match(r.problems[0].message, /must be one of/);
  r = validateOutputContract(m, [{ path: "/tmp/run/{out}/result.json", bytes: 10, sha256: "x", content_text: '{"status":"match"}' }]);
  assert.equal(r.ok, true);
  r = validateOutputContract(m, [{ path: "result.json", bytes: 0, sha256: "x", content_text: "" }]);
  assert.equal(r.ok, false, "empty file is not produced");
});

test("api keys: generated keys hash to what is stored and are never recoverable from the hash", () => {
  const k = generateApiKey();
  assert.ok(looksLikeApiKey(k.key));
  assert.equal(apiKeyHash(k.key), k.hash);
  assert.equal(k.prefix, k.key.slice(0, 14));
  assert.notEqual(generateApiKey().key, k.key);
  assert.equal(looksLikeApiKey("sf_live_short"), false);
  assert.equal(secretsEqual("abc", "abc"), true);
  assert.equal(secretsEqual("abc", "abd"), false);
  assert.equal(secretsEqual("abc", "abcd"), false);
});

const row = (over: Partial<ReleaseStateRow> = {}): ReleaseStateRow => ({
  version_id: "v", status: "draft", manifest_hash: "h".repeat(64), min_eval_pass_rate: 0.8, require_approval: true, eval_case_count: 2,
  current_eval_set_hash: "e1", latest_eval_run_id: "r", latest_eval_pass_rate: 1, latest_eval_set_hash: "e1", latest_eval_at: "t",
  eval_current: true, eval_gate_met: true, latest_approval_id: "a", latest_approval_decision: "approve", latest_approval_hash: "h".repeat(64),
  latest_approval_at: "t", latest_approval_reviewer: "u", latest_approval_note: "", approval_valid: true, approval_stale: false, publishable: true, ...over,
});

test("release state: gates and the single next action", () => {
  assert.equal(evalGate(row()).met, true);
  assert.equal(evalGate(row({ min_eval_pass_rate: 0 })).tone, "none");
  assert.equal(evalGate(row({ eval_case_count: 0 })).met, false);
  assert.equal(evalGate(row({ eval_current: false })).tone, "hold");
  assert.equal(evalGate(row({ latest_eval_pass_rate: "0.5" })).met, false);
  assert.equal(approvalGate(row()).met, true);
  const stale = approvalGate(row({ approval_valid: false, approval_stale: true, latest_approval_hash: "g".repeat(64) }));
  assert.equal(stale.met, false); assert.match(stale.detail, /Stale/);
  assert.match(approvalGate(row({ approval_valid: false, approval_stale: false, latest_approval_decision: "reject", latest_approval_note: "no" })).detail, /Rejected/);
  assert.equal(approvalGate(row({ require_approval: false, approval_valid: false })).met, true);

  assert.equal(nextAction(row({ status: "draft", eval_case_count: 0, latest_eval_run_id: null, eval_current: false, approval_valid: false, approval_stale: false, latest_approval_decision: null }), false).action, "test");
  assert.equal(nextAction(row({ status: "draft", eval_case_count: 0, latest_eval_run_id: null, eval_current: false, approval_valid: false, approval_stale: false, latest_approval_decision: null }), true).action, "add_cases");
  assert.equal(nextAction(row({ status: "draft", latest_eval_run_id: null, eval_current: false, approval_valid: false, approval_stale: false, latest_approval_decision: null }), true).action, "run_eval");
  assert.equal(nextAction(row({ status: "draft", approval_valid: false, approval_stale: false, latest_approval_decision: null }), true).action, "request_review");
  assert.equal(nextAction(row({ status: "in_review", approval_valid: false }), true).action, "review");
  assert.equal(nextAction(row({ status: "approved" }), true).action, "publish");
  assert.equal(nextAction(row({ status: "published" }), true).action, "new_draft");
});

test("roles", () => {
  assert.equal(can("consumer", "version.publish"), false);
  assert.equal(can("author", "version.publish"), true);
  assert.equal(can("author", "version.review"), false);
  assert.equal(can("reviewer", "version.review"), true);
  assert.equal(can("reviewer", "admin.keys"), false);
  assert.equal(can("admin", "admin.keys"), true);
  assert.equal(can("consumer", "run.published"), true);
  assert.equal(can("consumer", "run.any_version"), false);
  assert.equal(can(null, "audit.read"), false);
});

test("import from repo: every wired repo skill yields a valid manifest and its agent cases", () => {
  const skills = JSON.parse(readFileSync(new URL("../data/skills.json", import.meta.url), "utf8")) as RepoSkill[];
  let wired = 0, llm = 0, cases = 0;
  for (const s of skills) {
    if (!s.agent) continue;
    wired++;
    const r = manifestFromRepoSkill(s);
    assert.equal(r.ok, true, `${s.id}: ${!r.ok ? JSON.stringify(r.problems) : ""}`);
    if (!r.ok) continue;
    assert.ok(r.manifest.outputs.length > 0);
    assert.equal(r.manifest.run.length, s.agent.steps.length, `${s.id}: full run steps carried over`);
    if (r.manifest.run.some((x) => x.kind === "llm")) { llm++; assert.equal(r.manifest.model_config.provider, "anthropic"); assert.ok(r.manifest.connections.includes("anthropic")); }
    const cs = casesFromRepoSkill(s);
    cases += cs.length;
    for (const c of cs) for (const v of Object.values(c.inputs)) if (typeof v === "object") assert.match((v as { path: string }).path, /^evals\/fixtures\//);
  }
  assert.equal(wired, skills.filter((s) => s.agent).length);
  assert.ok(wired >= 40, `wired=${wired}`);
  assert.ok(llm > 0 && cases > 40, `llm=${llm} cases=${cases}`);
});

import { publicContract, stripRuntimePaths } from "../lib/factory/publicShape.ts";
test("consumer API contract drops workspace internals", () => {
  assert.deepEqual(publicContract({ slug: "x", workspace_id: "w", policy: { a: 1 }, skill_id: "s", version: 1 }), { slug: "x", version: 1 });
});
test("consumer API strips runtime paths from checks and steps", () => {
  const out = stripRuntimePaths({ checks: [{ path: "/tmp/sf/ac84-89/out/sizing.json", evidence: "/tmp/sf/ac84-89/out/sizing.json exists" }], steps: [{ cmd: "/var/lang/bin/python -I scripts/size.py --inputs /tmp/sf/ac84-89/inputs/inputs.txt" }] });
  assert.deepEqual(out, { checks: [{ path: "sizing.json", evidence: "sizing.json exists" }], steps: [{ cmd: "python -I scripts/size.py --inputs inputs/inputs.txt" }] });
});

import { checkPin, currentPin } from "../lib/factory/pins.ts";
test("content pin: drafts run current files; non-drafts must match their pin", () => {
  const id = "ai-platform/infra-gpu-sizing", now = currentPin(id)!;
  assert.ok(now && now.length === 64);
  assert.deepEqual(checkPin({ kind: "repo", repo_skill: id, content_sha: "x".repeat(64) }, "draft").ok, true);
  assert.equal(checkPin({ kind: "repo", repo_skill: id, content_sha: now }, "published").ok, true);
  const bad = checkPin({ kind: "repo", repo_skill: id, content_sha: "0".repeat(64) }, "approved");
  assert.equal(bad.ok, false);
  const legacy = checkPin({ kind: "repo", repo_skill: id }, "published");
  assert.ok(legacy.ok && legacy.note?.includes("before content pinning"));
  assert.equal(checkPin({ kind: "authored" }, "published").ok, true);
});

// ───────────────────────── composed agents ─────────────────────────
import { validateAgentSpec, autoWire, composeFile, resolveRef, newStepId, unusedInputs, type AgentSpec, type CatalogSkill, type StepRecord } from "../lib/factory/agents.ts";
import { execFileSync } from "node:child_process";

function agentCatalog(): Map<string, CatalogSkill> {
  const skills = JSON.parse(readFileSync(new URL("../data/skills.json", import.meta.url), "utf8")) as RepoSkill[];
  return new Map(skills.filter((s) => s.agent).map((s) => [s.id, {
    id: s.id, name: s.name, stage: (s as unknown as { stage: string | null }).stage, description: s.description,
    inputs: s.agent!.inputs.map((i) => ({ name: i.name, type: i.type, required: i.required, from: i.from, default: (i as { default?: string | null }).default ?? null })),
    outputs: s.agent!.outputs.map((o) => o.path),
  }]));
}

test("shipped agent templates validate in TypeScript exactly as in Python", () => {
  const cat = agentCatalog();
  for (const name of ["presales-pursuit", "ai-use-case-to-release"]) {
    const spec = JSON.parse(readFileSync(new URL(`../../agents/${name}/agent.json`, import.meta.url), "utf8")) as AgentSpec;
    assert.deepEqual(validateAgentSpec(spec, cat), [], name);
  }
});

test("validator reports wiring mistakes with the CLI's wording", () => {
  const spec = { name: "bad", description: "x", inputs: [{ name: "client", type: "string", required: true }], steps: [
    { id: "est", skill: "presales/effort-estimator", inputs: { client: "$in.client", nope: "1" } },
    { id: "prop", skill: "presales/proposal-writer", inputs: { win_themes: "$in.themes", estimate: "$steps.est:not-written.md", discovery: "$steps.later:x.md" } },
    { id: "gate", approval: { role: " " } },
  ] } as AgentSpec;
  const p = validateAgentSpec(spec, agentCatalog()).join("\n");
  for (const want of ["has no input 'nope'", "required input 'wbs'", "$in.themes is not a declared agent input", "does not declare 'not-written.md'", "refers to a step that does not run before it", "approval needs a role"]) assert.ok(p.includes(want), want);
});

test("auto-wiring maps a skill's inputs to earlier outputs, else to new agent inputs", () => {
  const cat = agentCatalog();
  const spec: AgentSpec = { name: "a", description: "d", inputs: [], steps: [] };
  for (const sk of ["presales/discovery-interview", "presales/effort-estimator", "presales/value-case-builder"]) {
    const w = autoWire(spec, cat.get(sk)!, cat);
    spec.inputs.push(...w.newAgentInputs);
    spec.steps.push({ id: newStepId(spec, sk), skill: sk, inputs: w.inputs });
  }
  const w = autoWire(spec, cat.get("presales/proposal-writer")!, cat);
  assert.equal(w.inputs.estimate, "$steps.effort-estimator:estimate.md");
  assert.equal(w.inputs.value_case, "$steps.value-case-builder:value-case.md");
  assert.equal(w.inputs.win_themes, "$in.win_themes");
  assert.deepEqual(w.newAgentInputs.map((i) => i.name), ["win_themes"]);
  spec.steps.push({ id: "proposal", skill: "presales/proposal-writer", inputs: w.inputs });
  spec.inputs.push(...w.newAgentInputs);
  assert.deepEqual(validateAgentSpec(spec, cat), []);
  assert.equal(newStepId(spec, "presales/proposal-writer"), "proposal-writer");
  assert.deepEqual(unusedInputs({ ...spec, inputs: [...spec.inputs, { name: "orphan", type: "string", required: false }] }), ["orphan"]);
});

test("compose output is byte-identical to run_agent.py do_compose (1.0 stays 1.0)", () => {
  const steps: StepRecord[] = [{ id: "ev", kind: "skill", status: "ok", files: [{ path: "s.json", bytes: 0, sha256: "", content_text: '{"overall": {"pass_rate": 1.0, "n": 38, "ok": true, "note": "a, \\"b\\""}}' }] }];
  const inputs = { extra: { kind: "text" as const, content: "# fictional\nkey,value,source,notes\nrollback_time_min,15,owner,\"x, y\"\npass_rate,0.1,owner,\n", ext: "csv" } };
  const c = { out: "facts.csv", format: "kv-csv" as const, include: "$in.extra", rows: { pass_rate: "$steps.ev:s.json#overall.pass_rate", n: "$steps.ev:s.json#overall.n", ok: "$steps.ev:s.json#overall.ok", note: "$steps.ev:s.json#overall.note", tier: "medium" } };
  const ts = composeFile(c, inputs, steps).content;
  const py = execFileSync("python3", ["-I", "-c", `
import json, sys, tempfile, pathlib
sys.path.insert(0, ${JSON.stringify(new URL("../../scripts", import.meta.url).pathname)})
import run_agent
d = pathlib.Path(tempfile.mkdtemp()); (d / "ev").mkdir(); (d / "out").mkdir()
(d / "ev" / "s.json").write_text(${JSON.stringify(steps[0].files![0].content_text)})
(d / "extra.csv").write_text(${JSON.stringify(inputs.extra.content)})
p = run_agent.do_compose(json.loads(${JSON.stringify(JSON.stringify(c))}), {"extra": str(d / "extra.csv")}, {"ev": d / "ev"}, d / "out")
sys.stdout.write(p.read_text())`], { encoding: "utf8" });
  assert.equal(ts, py);
  assert.match(ts, /^pass_rate,1\.0,/m);
  assert.throws(() => resolveRef("$steps.ev:s.json#overall.nope", {}, steps), /not found/);
});

test("autoWire: same-named agent input of a different type is not reused", async () => {
  const { autoWire } = await import("../lib/factory/agents.ts");
  const cat = new Map([["a/one", { id: "a/one", name: "one", stage: null, description: "", inputs: [{ name: "system", type: "csv", required: true, from: "", default: null }], outputs: [] }],
                       ["a/two", { id: "a/two", name: "two", stage: null, description: "", inputs: [{ name: "system", type: "string", required: false, from: "", default: null }, { name: "data", type: "csv", required: true, from: "", default: null }, { name: "mode", type: "csv", required: true, from: "", default: null }], outputs: [] }]]);
  const spec = { name: "x", description: "x", inputs: [{ name: "system", type: "csv", required: true, from: "" }, { name: "mode", type: "string", required: true, from: "" }], steps: [{ id: "one", skill: "a/one", inputs: { system: "$in.system" } }], outputs: [] };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = autoWire(spec as any, cat.get("a/two") as any, cat as any);
  assert.equal(w.inputs.system, undefined, "optional string 'system' must not be wired to the csv 'system'");
  assert.equal(w.inputs.mode, "$in.two_mode", "required csv 'mode' gets its own agent input");
  assert.deepEqual(w.newAgentInputs.map((i) => i.name).sort(), ["data", "two_mode"]);
});

test("humanInput: description without the layout path; falls back to the name", async () => {
  const { humanInput } = await import("../lib/factory/agents.ts");
  assert.equal(humanInput({ name: "system", from: "AI Act questionnaire (layout: skills/ai-platform/eu-ai-act-classifier/assets/system-questionnaire.csv)" }), "AI Act questionnaire");
  assert.equal(humanInput({ name: "as_of" }), "As of");
  assert.equal(humanInput({ name: "x", from: "review date YYYY-MM-DD" }), "review date YYYY-MM-DD");
});

test("exampleInputs: template first, then the consuming skill's own example", async () => {
  const { exampleInputs } = await import("../lib/factory/agents.ts");
  const spec = { inputs: [{ name: "system", type: "csv", required: true }, { name: "bom", type: "csv", required: true }, { name: "zzz", type: "csv", required: false }],
    steps: [{ id: "lic", skill: "ai-platform/ai-bom-license-check", inputs: { bom: "$in.bom" } }] };
  const tpl = [{ demo: { system: { kind: "value" as const, value: "T" } } }];
  const sd = { "ai-platform/ai-bom-license-check": { bom: { kind: "text" as const, content: "a,b", ext: "csv" } } };
  const d = exampleInputs(spec as never, tpl, sd)!;
  assert.deepEqual(Object.keys(d).sort(), ["bom", "system"]);
  assert.equal((d.bom as { content: string }).content, "a,b");
  assert.equal(exampleInputs({ inputs: [{ name: "q", type: "csv", required: true }], steps: [] } as never, tpl, sd), null);
});
