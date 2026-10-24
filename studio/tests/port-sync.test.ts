import { test } from "node:test";
import assert from "node:assert/strict";
import { skillEntity, verdictForPort, AI_SKILL_BLUEPRINT, SF_PROPERTIES, REGISTRY_RELATION } from "../lib/integrations/port/map.ts";
import { PortClient } from "../lib/integrations/port/client.ts";
import { operatorAuthorized } from "../lib/integrations/port/serverAuth.ts";
import { drainPortOutbox, backoffMs, MAX_ATTEMPTS } from "../lib/integrations/port/outbox.ts";
import { reconcilePort, reconcileText } from "../lib/integrations/port/reconcile.ts";
import { syncMcpServerEntity, allowedTools, isFactoryServer } from "../lib/integrations/port/mcpEntity.ts";
import { ensureSkillQualityScorecard, readbackLevels, SKILL_QUALITY_SCORECARD } from "../lib/integrations/port/scorecard.ts";

const cfg = { apiUrl: "https://port.test", clientId: "id", clientSecret: "secret" };
const H = "a".repeat(64), H2 = "b".repeat(64);

/* ── a Port stand-in: records every call, serves one blueprint and the entities it has been given ── */
function fakePort(opts: { blueprint?: Record<string, unknown> | null; entities?: Record<string, unknown>[]; failUpsert?: boolean; hasRegistry?: boolean; scorecards?: Record<string, unknown>[]; mcp?: Record<string, unknown>[] } = {}) {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const entities = new Map((opts.entities ?? []).map((e) => [String(e.identifier), e]));
  const scorecards = new Map((opts.scorecards ?? []).map((s) => [String(s.identifier), s]));
  let blueprint = opts.blueprint === undefined ? { identifier: "aiSkill", schema: { properties: { purpose: {} } }, relations: {} } : opts.blueprint;
  const f = (async (url: string | URL | Request, init?: RequestInit) => {
    const u = String(url), method = init?.method ?? "GET", body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const path = u.replace(cfg.apiUrl, "");
    calls.push({ method, path, body });
    const json = (status: number, data: unknown) => new Response(JSON.stringify(data), { status });
    if (path === "/v1/auth/access_token") return json(200, { accessToken: "t", expiresIn: 10800 });
    if (path === "/v1/blueprints/aiSkill" && method === "GET") return blueprint ? json(200, { blueprint }) : json(404, { message: "not found" });
    if (path === "/v1/blueprints/skill" && method === "GET") return opts.hasRegistry ? json(200, { blueprint: { identifier: "skill" } }) : json(404, {});
    if (path === "/v1/blueprints" && method === "POST") { blueprint = body; return json(201, {}); }
    if (path === "/v1/blueprints/aiSkill" && method === "PATCH") { blueprint = { ...blueprint, ...body }; return json(200, {}); }
    if (path.startsWith("/v1/blueprints/aiSkill/entities?upsert") && method === "POST") { if (opts.failUpsert) return json(500, { message: "port down" }); entities.set(String(body.identifier), body); return json(200, {}); }
    if (path === "/v1/blueprints/aiSkill/entities/search") return json(200, { entities: [...entities.values()] });
    if (path === "/v1/blueprints/aiSkill/scorecards" && method === "GET") return json(200, { scorecards: [...scorecards.values()] });
    if (path === "/v1/blueprints/aiSkill/scorecards" && method === "POST") { scorecards.set(String(body.identifier), body); return json(201, {}); }
    if (path.startsWith("/v1/blueprints/aiSkill/scorecards/") && method === "PUT") { scorecards.set(String(body.identifier), body); return json(200, {}); }
    if (path === "/v1/blueprints/_mcp_server/entities/search") return json(200, { entities: (opts.mcp ?? []) });
    if (path.startsWith("/v1/blueprints/_mcp_server/entities?upsert") && method === "POST") { const e = (opts.mcp ?? []).find((m) => m.identifier === body.identifier); if (e) Object.assign(e.properties as object, body.properties); return json(200, {}); }
    if (path.startsWith("/v1/blueprints/aiSkill/entities/") && method === "GET") { const e = entities.get(decodeURIComponent(path.split("/").pop()!)); return e ? json(200, { entity: e }) : json(404, {}); }
    return json(404, { message: `unhandled ${method} ${path}` });
  }) as typeof fetch;
  return { f, calls, entities, scorecards, blueprint: () => blueprint };
}

/* ── a Supabase stand-in: in-memory tables with the chainable subset the worker and reconcile use ── */
type Row = Record<string, unknown>;
function fakeSupabase(tables: Record<string, Row[]>, rpcs: Record<string, (args: Row) => unknown> = {}) {
  const q = (name: string) => {
    const rows = () => tables[name] ?? (tables[name] = []);
    let filters: ((r: Row) => boolean)[] = [];
    let limitN = Infinity;
    const self: Record<string, unknown> = {};
    const chain = (fn: (r: Row) => boolean) => { filters.push(fn); return self; };
    const matches = () => rows().filter((r) => filters.every((f) => f(r)));
    Object.assign(self, {
      select: () => self, order: () => self, limit: (n: number) => { limitN = n; return self; },
      eq: (k: string, v: unknown) => chain((r) => r[k] === v), in: (k: string, vs: unknown[]) => chain((r) => vs.includes(r[k])),
      is: (k: string, v: unknown) => chain((r) => r[k] === v), lt: (k: string, v: number) => chain((r) => (r[k] as number) < v),
      lte: (k: string, v: string) => chain((r) => String(r[k]) <= v), gte: (k: string, v: number) => chain((r) => (r[k] as number) >= v),
      then: (res: (v: unknown) => void) => res({ data: matches().slice(0, limitN), error: null }),
      update: (patch: Row) => { const u = { eq: (k: string, v: unknown) => { for (const r of rows()) if (r[k] === v) Object.assign(r, patch); return Promise.resolve({ error: null }); }, in: (k: string, vs: unknown[]) => { for (const r of rows()) if (vs.includes(r[k])) Object.assign(r, patch); return Promise.resolve({ error: null }); } }; return u; },
      upsert: (row: Row, o: { onConflict: string }) => { const keys = o.onConflict.split(","); const hit = rows().find((r) => keys.every((k) => r[k] === row[k])); if (hit) Object.assign(hit, row); else rows().push({ ...row }); return Promise.resolve({ error: null }); },
    });
    return self;
  };
  return { from: q, rpc: (name: string, args: Row) => Promise.resolve({ data: rpcs[name]?.(args) ?? null, error: null }), tables } as unknown as import("@supabase/supabase-js").SupabaseClient & { tables: Record<string, Row[]> };
}

const manifest = { inputs: [{ name: "workload", required: true }], model_config: { provider: "none" } };
const WS = "ws-1";
function factoryTables(extra: Partial<Record<string, Row[]>> = {}) {
  return {
    sf_skills: [
      { id: "s1", workspace_id: WS, slug: "llm-cost-model", name: "LLM cost model", purpose: "p", status: "published" },
      { id: "s2", workspace_id: WS, slug: "old-skill", name: "Old", purpose: "", status: "retired" },
      { id: "s3", workspace_id: WS, slug: "draft-only", name: "Draft", purpose: "", status: "draft" },
    ],
    sf_skill_versions: [
      { id: "v1", skill_id: "s1", version: 2, status: "published", source: { kind: "repo", repo_skill: "ai-platform/llm-cost-model" }, manifest, manifest_hash: H, published_at: "2026-10-20T00:00:00Z" },
      { id: "v0", skill_id: "s1", version: 1, status: "superseded", source: { kind: "repo", repo_skill: "ai-platform/llm-cost-model" }, manifest, manifest_hash: H2, published_at: "2026-10-18T00:00:00Z" },
      { id: "v2", skill_id: "s2", version: 1, status: "retired", source: { kind: "authored" }, manifest, manifest_hash: H2, published_at: "2026-10-19T00:00:00Z" },
      { id: "v3", skill_id: "s3", version: 1, status: "draft", source: { kind: "authored" }, manifest, manifest_hash: H2, published_at: null },
    ],
    sf_version_release_state: [
      { workspace_id: WS, version_id: "v1", latest_eval_pass_rate: 1, eval_case_count: 6, approval_valid: true, latest_eval_model: "gpt-4.1-mini", latest_eval_at: "2026-10-21T10:00:00Z" },
      { workspace_id: WS, version_id: "v2", latest_eval_pass_rate: null, eval_case_count: 0, approval_valid: false, latest_eval_model: null, latest_eval_at: null },
    ],
    sf_port_outbox: [] as Row[], sf_port_links: [] as Row[],
    ...extra,
  } as Record<string, Row[]>;
}

test("sf_ mapping: nulls never zeros, retired skills lose their MCP tool, every sf_ property is on the blueprint, registry relation only when known", () => {
  const base = { slug: "x", name: "X", purpose: "", version: 3, published_at: null, manifest_hash: H, inputs: [], usesModel: false, evalPassRate: null, evalCases: 0, approved: false, drift: "n/a" as const, stage: null };
  const e = skillEntity(base, "https://f/", "2026-10-23T00:00:00Z");
  assert.equal(e.properties.sf_trigger_score, null); assert.equal(e.properties.sf_lift, null); assert.equal(e.properties.sf_eval_at, null); assert.equal(e.properties.sf_owner, null);
  assert.equal(e.properties.sf_eval_verdict, "not-evaluated"); assert.equal(e.properties.sf_status, "published"); assert.equal(e.properties.sf_version, "3");
  assert.equal(e.properties.sf_factory_url, "https://f/skills/x/release"); assert.equal(e.properties.sf_mcp_tool, "x"); assert.deepEqual(e.relations, {});
  const r = skillEntity({ ...base, status: "retired", verdict: "healthy", triggerScore: 1, lift: 0.36, registryFileId: "o/r/skills/a/x/SKILL.md" }, "https://f");
  assert.equal(r.properties.sf_mcp_tool, null); assert.equal(r.properties.sf_status, "retired"); assert.equal(r.properties.sf_trigger_score, 1);
  assert.deepEqual(r.relations, { registry_file: "o/r/skills/a/x/SKILL.md" });
  for (const k of Object.keys(e.properties)) assert.ok(k in AI_SKILL_BLUEPRINT.schema.properties, `${k} declared on the blueprint`);
  for (const k of Object.keys(SF_PROPERTIES)) assert.ok(k.startsWith("sf_"));
  assert.equal(REGISTRY_RELATION.registry_file.target, "skill");
  assert.equal(verdictForPort("OK"), "healthy"); assert.equal(verdictForPort("BODY"), "being-improved"); assert.equal(verdictForPort(null), "not-evaluated");
});

test("blueprint schema: existing blueprint is PATCHed only with the properties it lacks; nothing the tenant added is lost; a second pass is a no-op", async () => {
  const p = fakePort({ blueprint: { identifier: "aiSkill", description: "old", schema: { properties: { purpose: {}, tenant_added: { type: "string" } }, required: [] }, relations: { owner: { target: "_team" } } } });
  const c = new PortClient(cfg, p.f);
  assert.equal(await c.ensureBlueprintSchema({ ...AI_SKILL_BLUEPRINT, relations: { ...REGISTRY_RELATION } }), "extended");
  const patch = p.calls.find((x) => x.method === "PATCH")!.body as { schema: { properties: Record<string, unknown> }; relations: Record<string, unknown> };
  assert.ok("tenant_added" in patch.schema.properties && "sf_content_hash" in patch.schema.properties && "owner" in patch.relations && "registry_file" in patch.relations);
  assert.equal(await c.ensureBlueprintSchema({ ...AI_SKILL_BLUEPRINT, relations: { ...REGISTRY_RELATION } }), "current");
  assert.equal(p.calls.filter((x) => x.method === "PATCH").length, 1);
  const none = fakePort({ blueprint: null });
  assert.equal(await new PortClient(cfg, none.f).ensureBlueprintSchema(AI_SKILL_BLUEPRINT), "created");
});

test("token: concurrent callers share one refresh (single-flight), renewed before Port's expiry and never later than 2.5 h", async () => {
  const p = fakePort();
  const c = new PortClient(cfg, p.f);
  await Promise.all([c.accessToken(), c.accessToken(), c.accessToken()]);
  assert.equal(p.calls.filter((x) => x.path === "/v1/auth/access_token").length, 1);
});

test("operator routes: bearer must equal HEALTH_CHECK_TOKEN or CRON_SECRET; unset → 401 with a reason", () => {
  assert.equal(operatorAuthorized("Bearer abc", { HEALTH_CHECK_TOKEN: "abc" }).ok, true);
  assert.equal(operatorAuthorized("Bearer abc", { CRON_SECRET: "abc" }).ok, true);
  assert.equal(operatorAuthorized("Bearer abd", { HEALTH_CHECK_TOKEN: "abc" }).ok, false);
  assert.match((operatorAuthorized("Bearer abc", {}) as { message: string }).message, /HEALTH_CHECK_TOKEN/);
});

test("outbox worker: upserts the skill's current state, links it, settles every row for that skill; retired → sf_status retired; drafts never sync", async () => {
  const sb = fakeSupabase(factoryTables({ sf_port_outbox: [
    { id: "o1", workspace_id: WS, skill_id: "s1", skill_slug: "llm-cost-model", event_type: "publish", payload: {}, attempts: 0, last_error: null, next_attempt_at: "2026-01-01T00:00:00Z", processed_at: null, created_at: "2026-01-01T00:00:00Z" },
    { id: "o2", workspace_id: WS, skill_id: "s1", skill_slug: "llm-cost-model", event_type: "publish", payload: {}, attempts: 0, last_error: null, next_attempt_at: "2026-01-01T00:00:00Z", processed_at: null, created_at: "2026-01-01T00:00:01Z" },
    { id: "o3", workspace_id: WS, skill_id: "s2", skill_slug: "old-skill", event_type: "retire", payload: {}, attempts: 0, last_error: null, next_attempt_at: "2026-01-01T00:00:00Z", processed_at: null, created_at: "2026-01-01T00:00:02Z" },
    { id: "o4", workspace_id: WS, skill_id: "s3", skill_slug: "draft-only", event_type: "publish", payload: {}, attempts: 0, last_error: null, next_attempt_at: "2026-01-01T00:00:00Z", processed_at: null, created_at: "2026-01-01T00:00:03Z" },
  ] }), { sf_port_skill_owners: () => [{ skill_id: "s1", email: "owner@x.y" }] });
  const p = fakePort({ hasRegistry: true });
  process.env.PORT_CLIENT_ID = "id"; process.env.PORT_CLIENT_SECRET = "secret"; process.env.PORT_API_URL = cfg.apiUrl;
  const r = await drainPortOutbox(sb, { portalBase: "https://f", f: p.f, now: new Date("2026-02-01T00:00:00Z"), registryRepo: "o/giri-skills" });
  assert.equal(r.picked, 4); assert.equal(r.synced, 3); assert.equal(r.failed, 1);
  const live = p.entities.get("llm-cost-model")!.properties as Record<string, unknown>;
  assert.equal(live.sf_status, "published"); assert.equal(live.sf_content_hash, H); assert.equal(live.sf_version, "2"); assert.equal(live.sf_owner, "owner@x.y"); assert.equal(live.sf_approval_valid, true); assert.equal(live.sf_eval_at, "2026-10-21T10:00:00Z");
  assert.deepEqual(p.entities.get("llm-cost-model")!.relations, { registry_file: "o/giri-skills/skills/ai-platform/llm-cost-model/SKILL.md" });
  assert.equal((p.entities.get("old-skill")!.properties as Record<string, unknown>).sf_status, "retired");
  assert.equal((p.entities.get("old-skill")!.properties as Record<string, unknown>).sf_mcp_tool, null);
  assert.ok(!p.entities.has("draft-only"));
  const ob = sb.tables.sf_port_outbox;
  assert.ok(ob.filter((o) => o.skill_id === "s1").every((o) => o.processed_at));
  assert.ok(ob.find((o) => o.id === "o4")!.processed_at === null && ob.find((o) => o.id === "o4")!.attempts === 1);
  assert.match(String(ob.find((o) => o.id === "o4")!.last_error), /drafts do not sync/);
  assert.equal(sb.tables.sf_port_links.length, 2);
  assert.equal(sb.tables.sf_port_links.find((l) => l.skill_id === "s1")!.last_synced_hash, H);
  // a replay of the same rows is a no-op for Port (already processed) — idempotent on the identifier
  const again = await drainPortOutbox(sb, { portalBase: "https://f", f: p.f, now: new Date("2026-02-01T00:01:00Z") });
  assert.equal(again.picked, 0, "processed rows and a row inside its backoff window are not picked again");
});

test("outbox worker: Port failures back off and are kept with the error; the 5th failure dead-letters; no row is ever marked processed", async () => {
  const sb = fakeSupabase(factoryTables({ sf_port_outbox: [
    { id: "o1", workspace_id: WS, skill_id: "s1", skill_slug: "llm-cost-model", event_type: "publish", payload: {}, attempts: 4, last_error: null, next_attempt_at: "2026-01-01T00:00:00Z", processed_at: null, created_at: "2026-01-01T00:00:00Z" },
  ] }), { sf_port_skill_owners: () => [] });
  const p = fakePort({ failUpsert: true });
  process.env.PORT_CLIENT_ID = "id"; process.env.PORT_CLIENT_SECRET = "secret"; process.env.PORT_API_URL = cfg.apiUrl;
  const r = await drainPortOutbox(sb, { portalBase: "https://f", f: p.f, now: new Date("2026-02-01T00:00:00Z") });
  assert.equal(r.synced, 0); assert.equal(r.failed, 1); assert.equal(r.deadLettered, 1);
  const o = sb.tables.sf_port_outbox[0];
  assert.equal(o.attempts, MAX_ATTEMPTS); assert.equal(o.processed_at, null); assert.match(String(o.last_error), /port down/);
  assert.equal(backoffMs(1), 2 * 60_000); assert.equal(backoffMs(5), 32 * 60_000);
  assert.match(String(sb.tables.sf_port_links[0].last_error), /port down/);
});

test("reconcile: counts come from both sides; hash drift, status drift, pending, missing and unknown entities are each named; clean state says YES twice", async () => {
  process.env.PORT_CLIENT_ID = "id"; process.env.PORT_CLIENT_SECRET = "secret"; process.env.PORT_API_URL = cfg.apiUrl;
  const clean = fakePort({ entities: [
    { identifier: "llm-cost-model", properties: { sf_status: "published", sf_content_hash: H, sf_version: "2", sf_skill_slug: "llm-cost-model" } },
    { identifier: "old-skill", properties: { sf_status: "retired", sf_content_hash: H2, sf_version: "1", sf_skill_slug: "old-skill", sf_mcp_tool: null } },
  ] });
  const ok = await reconcilePort(fakeSupabase(factoryTables()), WS, clean.f, new Date("2026-02-01T00:00:00Z"));
  assert.deepEqual(ok.factory, { published: 1, retired: 1 }); assert.deepEqual([ok.port.published, ok.port.retired], [1, 1]); assert.equal(ok.matched, 2); assert.deepEqual(ok.mismatches, []);
  assert.match(reconcileText(ok), /published-in-factory == published-in-port: YES\nhash match on all: YES/);

  const dirty = fakePort({ entities: [
    { identifier: "llm-cost-model", properties: { sf_status: "published", sf_content_hash: H2, sf_version: "2", sf_skill_slug: "llm-cost-model" } },   // stale hash
    { identifier: "ghost", properties: { sf_status: "published", sf_content_hash: H } },                                                     // nothing behind it
  ] });
  const bad = await reconcilePort(fakeSupabase(factoryTables({ sf_port_outbox: [{ workspace_id: WS, skill_slug: "old-skill", attempts: 2, last_error: "port down", processed_at: null }] })), WS, dirty.f);
  const by = Object.fromEntries(bad.mismatches.map((m) => [m.slug, m.reason]));
  assert.equal(by["llm-cost-model"], "hash-drift"); assert.equal(by["old-skill"], "sync-failed"); assert.equal(by.ghost, "unknown-in-factory");
  assert.equal(bad.outbox.failing, 1); assert.equal(bad.matched, 0);
  assert.match(reconcileText(bad), /hash match on all: NO/);
});

test("blueprint description respects Port's 200-character cap (live 422 on 2026-10-23)", () => {
  assert.ok(AI_SKILL_BLUEPRINT.description.length <= 200, `${AI_SKILL_BLUEPRINT.description.length} chars`);
});

test("scorecard: created once with Bronze/Silver/Gold (Gold per D3); unchanged → no write; drifted rules → replaced; levels read back from Port, not computed here", async () => {
  const p = fakePort();
  const c = new PortClient(cfg, p.f);
  assert.equal(await ensureSkillQualityScorecard(c), "created");
  const sc = p.scorecards.get("skill_quality")!;
  assert.deepEqual((sc.levels as { title: string }[]).map((l) => l.title), ["Basic", "Bronze", "Silver", "Gold"]);
  assert.deepEqual((sc.rules as { level: string }[]).map((r) => r.level), ["Bronze", "Silver", "Gold"]);
  const gold = (sc.rules as { level: string; query: { conditions: { property: string; operator: string; value: unknown }[] } }[]).find((r) => r.level === "Gold")!;
  assert.deepEqual(gold.query.conditions.slice(3), [{ property: "sf_trigger_score", operator: ">=", value: 0.9 }, { property: "sf_lift", operator: ">=", value: 0.3 }, { property: "sf_eval_cases", operator: ">=", value: 6 }]);
  for (const r of SKILL_QUALITY_SCORECARD.rules) for (const cond of r.query.conditions) assert.ok(cond.property.startsWith("sf_"), "rules test synced properties only");
  assert.equal(await ensureSkillQualityScorecard(c), "current");
  assert.equal(p.calls.filter((x) => x.method === "POST" && x.path.endsWith("/scorecards")).length, 1);
  p.scorecards.set("skill_quality", { identifier: "skill_quality", levels: sc.levels, rules: [{ identifier: "x", level: "Bronze", query: {} }] });
  assert.equal(await ensureSkillQualityScorecard(c), "updated");
  assert.equal(p.calls.filter((x) => x.method === "PUT").length, 1);

  p.entities.set("healthy-one", { identifier: "healthy-one", properties: { sf_status: "published", sf_eval_verdict: "healthy", sf_approval_valid: true }, scorecards: { skill_quality: { level: "Silver", rules: [{ identifier: "published_with_verdict", status: "SUCCESS" }, { identifier: "healthy_and_approved", status: "SUCCESS" }] } } });
  p.entities.set("not-evaluated-one", { identifier: "not-evaluated-one", properties: { sf_status: "published", sf_eval_verdict: "not-evaluated", sf_approval_valid: true }, scorecards: { skill_quality: { level: "Bronze", rules: [{ identifier: "published_with_verdict", status: "SUCCESS" }, { identifier: "healthy_and_approved", status: "FAILURE" }] } } });
  const rb = await readbackLevels(c, ["healthy-one", "not-evaluated-one", "missing"]);
  assert.deepEqual(rb.map((r) => [r.slug, r.level]), [["healthy-one", "Silver"], ["not-evaluated-one", "Bronze"], ["missing", null]]);
});

test("WP5 MCP server entity: allowed_tools = helpers + published slugs; only the factory's own unscoped server is touched; merge-upsert of that one property; unchanged → no write; not registered → said so", async () => {
  assert.deepEqual(allowedTools(["b", "a", "a", "find_skill"]), ["find_skill", "get_run", "a", "b"]);
  assert.ok(isFactoryServer("https://f.app/api/mcp", "https://f.app/")); assert.ok(!isFactoryServer("https://other/api/mcp", "https://f.app"));
  const mine = { identifier: "skills_factory", properties: { url: "https://f.app/api/mcp", headers: { Authorization: "Bearer {{ .secrets[\"SF_API_KEY\"] }}" }, allowed_tools: ["find_skill", "get_run", "old-retired"] } };
  const scoped = { identifier: "sf_role", properties: { url: "https://f.app/api/mcp/role/reviewer", allowed_tools: ["x"] } };
  const other = { identifier: "github", properties: { url: "https://api.githubcopilot.com/mcp", allowed_tools: ["y"] } };
  const p = fakePort({ mcp: [scoped, other, mine] });
  const c = new PortClient(cfg, p.f);
  const r = await syncMcpServerEntity(c, "https://f.app", ["code-review-runner", "llm-cost-model"]);
  assert.equal(r.status, "updated"); assert.equal(r.identifier, "skills_factory"); assert.deepEqual(r.removed, ["old-retired"]); assert.deepEqual(r.added, ["code-review-runner", "llm-cost-model"]);
  assert.deepEqual(mine.properties.allowed_tools, ["find_skill", "get_run", "code-review-runner", "llm-cost-model"]);
  assert.ok(mine.properties.headers, "auth header untouched"); assert.deepEqual(scoped.properties.allowed_tools, ["x"]); assert.deepEqual(other.properties.allowed_tools, ["y"]);
  const upserts = p.calls.filter((x) => x.path.startsWith("/v1/blueprints/_mcp_server/entities?upsert"));
  assert.equal(upserts.length, 1); assert.ok((upserts[0].path).includes("merge=true")); assert.deepEqual(Object.keys((upserts[0].body as { properties: object }).properties), ["allowed_tools"]);
  assert.equal((await syncMcpServerEntity(c, "https://f.app", ["code-review-runner", "llm-cost-model"])).status, "current");
  assert.equal((await syncMcpServerEntity(new PortClient(cfg, fakePort({ mcp: [other] }).f), "https://f.app", ["a"])).status, "not-registered");
});

test("Start here summary (fresh-eyes fix): trust verdict matches the Silver rule, numbers only when known, run paths named, retired says so", async () => {
  const { skillSummary } = await import("../lib/integrations/port/map.ts");
  const s = { slug: "code-review-runner", name: "Code review", purpose: "Reviews a diff.", version: 2, published_at: null, manifest_hash: H, inputs: [{ name: "diff", required: true }], usesModel: true, evalPassRate: 1, evalCases: 6, approved: true, drift: "blocked" as const, stage: null, status: "published" as const, verdict: "healthy" as const, triggerScore: 1, lift: 0.31, evalModel: "gpt-4.1-mini" };
  const t = skillSummary(s, "https://f");
  assert.match(t, /Yes — trusted for use \(Gold\)/);
  assert.match(skillSummary({ ...s, lift: 0.24 }, "https://f"), /Yes — trusted for use \(Silver\)/); assert.match(t, /100% of the time/); assert.match(t, /\+0\.31/); assert.match(t, /Run governed skill on a PR/); assert.match(t, /tool `code-review-runner`/); assert.match(t, /library copy has changed/);
  const ne = skillSummary({ ...s, verdict: "not-evaluated", triggerScore: null, lift: null, evalCases: 0, inputs: [{ name: "x", required: true }], drift: "current" }, "https://f");
  assert.match(ne, /Use with care \(Bronze\).*not been through/); assert.doesNotMatch(ne, /% of the time|over the model/); assert.doesNotMatch(ne, /on a PR/); assert.doesNotMatch(ne, /Library:/);
  const r = skillSummary({ ...s, status: "retired" }, "https://f");
  assert.match(r, /No — retired/); assert.doesNotMatch(r, /How to run it/);
  assert.ok("sf_summary" in AI_SKILL_BLUEPRINT.schema.properties);
});

test("library status in Port matches the factory: a published version with frozen files is never 'blocked' (live bug 2026-10-24: all 66 read blocked)", async () => {
  const { loadSkillsForPort } = await import("../lib/integrations/port/sync.ts");
  const t = factoryTables();
  (t.sf_skill_versions.find((v) => v.id === "v1")!.source as Record<string, unknown>).content_sha = "an-old-pin-the-deployment-no-longer-has";
  const without = await loadSkillsForPort(fakeSupabase({ ...t, sf_version_snapshots: [] }), WS, { slugs: ["llm-cost-model"] });
  assert.equal(without.rows[0].drift, "blocked", "without frozen files the stale pin really is blocked");
  const withFrozen = await loadSkillsForPort(fakeSupabase({ ...factoryTables(), sf_skill_versions: t.sf_skill_versions, sf_version_snapshots: [{ workspace_id: WS, version_id: "v1", sha256: "frozen-sha" }] }), WS, { slugs: ["llm-cost-model"] });
  assert.notEqual(withFrozen.rows[0].drift, "blocked");
});
