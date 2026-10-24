import { test } from "node:test";
import assert from "node:assert/strict";
import { portSignature, verifyPortSignature } from "../lib/integrations/port/signature.ts";
import { skillEntity, parsePortRun, runSkillAction, runSkillWorkflow, runSkillOnRepoWorkflow, runEntity, SKILL_RUN_BLUEPRINT, AI_SKILL_BLUEPRINT, portId, KNOWN_ACTIONS } from "../lib/integrations/port/map.ts";
import { fullNameFromUrl } from "../lib/integrations/port/repoRun.ts";
import { PortClient, portConfig } from "../lib/integrations/port/client.ts";

test("port signature: HMAC-SHA256 over `ts.body`, base64, `v1,` prefix; stale, tampered and unsigned requests rejected", () => {
  const body = '{"port_run_id":"r_1234"}', ts = "1792500000";
  const sig = `v1,${portSignature("s3cret", ts, body)}`;
  assert.equal(verifyPortSignature({ secret: "s3cret", timestamp: ts, signature: sig, rawBody: body, nowSec: 1792500010 }), null);
  assert.match(verifyPortSignature({ secret: "s3cret", timestamp: ts, signature: sig, rawBody: body + " ", nowSec: 1792500010 })!, /mismatch/);
  assert.match(verifyPortSignature({ secret: "other", timestamp: ts, signature: sig, rawBody: body, nowSec: 1792500010 })!, /mismatch/);
  assert.match(verifyPortSignature({ secret: "s3cret", timestamp: ts, signature: sig, rawBody: body, nowSec: 1792500000 + 3600 })!, /window/);
  assert.match(verifyPortSignature({ secret: "s3cret", timestamp: null, signature: sig, rawBody: body, nowSec: 0 })!, /missing/);
});

test("port mapping: one entity per published skill; percentages and library status readable; ids safe", () => {
  const e = skillEntity({ slug: "llm-cost-model", name: "LLM cost model", purpose: "p", version: 2, published_at: "2026-10-20T18:04:00Z", manifest_hash: "aa", inputs: [{ name: "workload", required: true }, { name: "actuals", required: false }], usesModel: false, evalPassRate: 1, evalCases: 6, approved: true, drift: "n/a", stage: "operate" }, "https://x.vercel.app/");
  assert.equal(e.identifier, "llm-cost-model");
  assert.equal(e.properties.eval_pass_rate, 100);
  assert.equal(e.properties.library_status, "current");
  assert.deepEqual(e.properties.inputs, ["workload", "actuals (optional)"]);
  assert.equal(e.properties.portal_url, "https://x.vercel.app/skills/llm-cost-model");
  for (const k of Object.keys(e.properties)) assert.ok(k in AI_SKILL_BLUEPRINT.schema.properties, `${k} is declared on the blueprint`);
  assert.equal(portId("a b/c"), "a-b-c");
  const a = runSkillAction("https://x/api/port/actions");
  assert.equal(a.trigger.blueprintIdentifier, "aiSkill");
  assert.equal(a.invocationMethod.body.port_run_id, "{{ .run.id }}");
});

test("port webhook body: inputs as object or JSON string; malformed ids and inputs refused", () => {
  const ok = parsePortRun({ port_run_id: "r_abc123", skill: "llm-cost-model", inputs: '{"workload":"a,b"}', requested_by: "x@y.z" });
  assert.ok(typeof ok !== "string" && ok.inputs.workload === "a,b");
  assert.equal(typeof parsePortRun({ port_run_id: "r_abc123", skill: "llm-cost-model", inputs: { workload: "a" } }), "object");
  assert.match(parsePortRun({ port_run_id: "r_abc123", skill: "../etc", inputs: {} }) as string, /skill/);
  assert.match(parsePortRun({ port_run_id: "r_abc123", skill: "x-y", inputs: "{bad" }) as string, /JSON/);
  assert.match(parsePortRun({ port_run_id: "r_abc123", skill: "x-y", inputs: [1] }) as string, /object/);
});

test("port client: token once, blueprint 409 = exists, upsert with merge, run logs and status; errors name the call", async () => {
  const calls: string[] = [];
  const f = (async (url: string, init: RequestInit) => {
    const u = new URL(url); calls.push(`${init.method} ${u.pathname}${u.search}`);
    const j = (o: unknown, status = 200) => new Response(JSON.stringify(o), { status });
    if (u.pathname === "/v1/auth/access_token") { assert.deepEqual(JSON.parse(String(init.body)), { clientId: "id", clientSecret: "sec" }); return j({ accessToken: "tok", expiresIn: 3600 }); }
    assert.equal((init.headers as Record<string, string>).authorization, "Bearer tok");
    if (u.pathname === "/v1/blueprints") return j({ ok: false, message: "exists" }, 409);
    if (u.pathname.endsWith("/entities")) return j({ ok: true }, 201);
    if (u.pathname.endsWith("/logs")) return j({ ok: true });
    if (init.method === "PATCH") return j({ message: "run already terminated" }, 422);
    return j({}, 404);
  }) as unknown as typeof fetch;
  const cfg = portConfig({ PORT_CLIENT_ID: "id", PORT_CLIENT_SECRET: "sec", PORT_API_URL: "https://api.us.port.io/" });
  assert.ok(cfg.ok);
  const c = new PortClient(cfg as never, f);
  assert.equal(await c.ensureBlueprint({ identifier: "aiSkill" }), "exists");
  await c.upsertEntity("aiSkill", { identifier: "s" });
  await c.runLog("r_1", "hi", { status: "SUCCESS", label: "ok" });
  await assert.rejects(c.runUpdate("r_1", { link: ["https://x"] }), /Port update run r_1 failed \(422\): run already terminated/);
  assert.equal(calls.filter((x) => x.includes("access_token")).length, 1, "token reused");
  assert.ok(calls.includes("POST /v1/blueprints/aiSkill/entities?upsert=true&merge=true"));
  assert.ok(calls.includes("POST /v1/actions/runs/r_1/logs"));
  assert.deepEqual(portConfig({}), { ok: false, missing: ["PORT_CLIENT_ID", "PORT_CLIENT_SECRET"] });
});

test("port workflow: entity input as object/JSON/identifier; sync mode; workflow wiring", () => {
  for (const skill of [{ identifier: "llm-cost-model", title: "LLM cost model" }, '{"identifier":"llm-cost-model"}', "llm-cost-model"]) {
    const r = parsePortRun({ mode: "sync", port_run_id: "wfr_ab12cd", skill, inputs: { workload: "x" } });
    assert.ok(typeof r !== "string" && r.skill === "llm-cost-model" && r.sync, JSON.stringify(skill));
  }
  const w = runSkillWorkflow("https://x/api/port/actions");
  assert.equal(w.nodes[0].config.type, "SELF_SERVE_TRIGGER");
  assert.equal((w.nodes[0].config as { userInputs: { properties: { skill: { blueprint: string } } } }).userInputs.properties.skill.blueprint, "aiSkill");
  assert.equal(w.nodes[1].config.type, "WEBHOOK");
  assert.match(JSON.stringify(w.nodes[1].config), /SF_API_KEY/);
  assert.deepEqual(w.connections[0], { sourceIdentifier: "trigger", targetIdentifier: "run_in_skills_factory", description: null });
});

test("port client: entities paged through search (limit/from), falling back to the list route", async () => {
  const seen: string[] = [];
  const f = (async (url: string, init: RequestInit) => {
    const u = new URL(url); seen.push(`${init.method} ${u.pathname}`);
    const j = (o: unknown, status = 200) => new Response(JSON.stringify(o), { status });
    if (u.pathname.endsWith("access_token")) return j({ accessToken: "t" });
    if (u.pathname === "/v1/blueprints") return j({ ok: true, blueprints: [{ identifier: "a" }, { identifier: "b" }] });
    if (u.pathname === "/v1/blueprints/a/entities/search") { const b = JSON.parse(String(init.body)); return j(b.from ? { entities: [{ identifier: "a2" }], next: null } : { entities: [{ identifier: "a1" }], next: "c1" }); }
    if (u.pathname === "/v1/blueprints/b/entities/search") return j({}, 404);
    if (u.pathname === "/v1/blueprints/b/entities") return j({ ok: true, entities: [{ identifier: "b1" }] });
    return j({}, 404);
  }) as unknown as typeof fetch;
  const c = new PortClient({ apiUrl: "https://api.port.io", clientId: "i", clientSecret: "s" }, f);
  assert.deepEqual((await c.listBlueprints()).map((b) => b.identifier), ["a", "b"]);
  assert.deepEqual((await c.listEntities("a")).entities.map((e) => e.identifier), ["a1", "a2"]);
  assert.deepEqual((await c.listEntities("b")).entities.map((e) => e.identifier), ["b1"]);
});

test("port webhook body (WP3): action identifier parsed and allow-listed; both action and workflow templates carry it; target kept for WP4", () => {
  const ok = parsePortRun({ action: "run_ai_skill", port_run_id: "r_abc123", skill: "x-y", inputs: {}, target: "giri-skills" });
  assert.ok(typeof ok !== "string" && ok.action === "run_ai_skill" && ok.target === "giri-skills");
  assert.equal((parsePortRun({ port_run_id: "r_abc123", skill: "x-y", inputs: {} }) as { action: string | null }).action, null, "legacy bodies without an action still parse (receiver logs them)");
  assert.match(parsePortRun({ action: "bad id!", port_run_id: "r_abc123", skill: "x-y", inputs: {} }) as string, /action/);
  assert.ok(!KNOWN_ACTIONS.has("delete_everything") && KNOWN_ACTIONS.has("run_ai_skill"));
  assert.equal(runSkillAction("https://x").invocationMethod.body.action, "run_ai_skill");
  const wf = runSkillWorkflow("https://x");
  const webhook = wf.nodes.find((n) => n.config.type === "WEBHOOK")!.config as { body: { action: string; port_run_id: string } };
  assert.equal(webhook.body.action, "run_ai_skill"); assert.equal(webhook.body.port_run_id, "{{ .workflowRun.identifier }}");
});

test("port webhook body: a key-shaped port_run_id is refused so a secret can never be persisted as an idempotency key", () => {
  assert.match(parsePortRun({ action: "run_ai_skill", port_run_id: "sf_live_abcdefghijklmnop", skill: "x-y", inputs: {} }) as string, /API key/);
});

test("WP4 run entity: deterministic id, relations to skill + repository + user, factory status words kept, started_at from duration, nulls not zeros", () => {
  const base = { runId: "807815d7-8d45-49fd-97a3-af023f477cd7", slug: "code-review-runner", version: 2, manifestHash: "d8".repeat(32), status: "failed", checksPassed: 5, checksTotal: 6, durationMs: 1840, finishedAt: "2026-10-24T02:00:00.000Z", factoryUrl: "https://f/runs/807815d7", portRunId: "wfr_X", repository: "giri-skills", pr: 162, headSha: "abc123", prUrl: "https://github.com/o/r/pull/162", requestedBy: "a@b.c" };
  const e = runEntity(base);
  assert.equal(e.identifier, "run_807815d7-8d45-49fd-97a3-af023f477cd7");
  assert.deepEqual(e.relations, { skill: "code-review-runner", target: "giri-skills", triggered_by: "a@b.c" });
  assert.equal(e.properties.sf_status, "failed"); assert.equal(e.properties.sf_checks, "5/6"); assert.equal(e.properties.sf_skill_version, "2");
  assert.equal(e.properties.sf_started_at, "2026-10-24T01:59:58.160Z"); assert.equal(e.properties.sf_duration_s, 1.8);
  for (const k of Object.keys(e.properties)) assert.ok(k in SKILL_RUN_BLUEPRINT.schema.properties, `${k} declared`);
  for (const k of Object.keys(e.relations)) assert.ok(k in SKILL_RUN_BLUEPRINT.relations, `${k} relation declared`);
  const bare = runEntity({ ...base, repository: null, pr: null, headSha: null, prUrl: null, requestedBy: null, durationMs: null, status: "weird" }, { withUser: false });
  assert.deepEqual(bare.relations, { skill: "code-review-runner" }); assert.equal(bare.properties.sf_started_at, null); assert.equal(bare.properties.sf_status, "failed", "unknown status never invented");
  assert.ok(SKILL_RUN_BLUEPRINT.description.length <= 200);
});

test("WP4 repo workflow + body: repository/PR/skill inputs; body carries action, target, pr; parser normalises entity inputs and PR numbers", () => {
  const wf = runSkillOnRepoWorkflow("https://x/api/port/actions");
  assert.equal(wf.identifier, "run_sf_skill_on_repo"); assert.ok(KNOWN_ACTIONS.has("run_sf_skill_on_repo"));
  const body = (wf.nodes[1].config as { body: Record<string, string> }).body;
  assert.equal(body.action, "run_sf_skill_on_repo"); assert.equal(body.target, "{{ .outputs.trigger.repository }}"); assert.equal(body.pr, "{{ .outputs.trigger.pr }}");
  const p = parsePortRun({ action: "run_sf_skill_on_repo", port_run_id: "wfr_abc1", skill: { identifier: "code-review-runner" }, target: '{"identifier":"giri-skills"}', pr: "#162", inputs: "" });
  assert.ok(typeof p !== "string"); assert.equal(p.target, "giri-skills"); assert.equal(p.pr, 162); assert.deepEqual(p.inputs, {});
  assert.match(parsePortRun({ action: "run_sf_skill_on_repo", port_run_id: "wfr_abc1", skill: "x-y", target: "r", pr: "abc", inputs: {} }) as string, /pull request number/);
  assert.equal(fullNameFromUrl("https://github.com/giritharanchockalingam/giri-skills"), "giritharanchockalingam/giri-skills");
  assert.equal(fullNameFromUrl("https://github.com/o/r.git/"), "o/r"); assert.equal(fullNameFromUrl("https://gitlab.com/o/r"), null);
});
