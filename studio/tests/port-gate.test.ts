import { test } from "node:test";
import assert from "node:assert/strict";
import { PortClient } from "../lib/integrations/port/client.ts";
import { runEntity, prEntityId, PR_REVIEW_AGGREGATION, PR_REVIEW_GATE_SCORECARD, SKILL_RUN_BLUEPRINT } from "../lib/integrations/port/map.ts";
import { recordRunInPort, supersedeHeadReviews, resolveTriggerEmail } from "../lib/integrations/port/repoRun.ts";

const cfg = { apiUrl: "https://port.test", clientId: "id", clientSecret: "secret" };

/* A Port stand-in for the WP6 surface: blueprints, scorecards, sf_skill_run upsert/search, workflow runs, users. */
function fake(opts: { refuse?: (body: Record<string, unknown>) => string | null; runs?: Record<string, unknown>[] } = {}) {
  const calls: { method: string; path: string; body?: Record<string, unknown> }[] = [];
  const blueprints: Record<string, Record<string, unknown>> = { githubPullRequest: { identifier: "githubPullRequest", schema: { properties: { status: {} } }, relations: {}, aggregationProperties: { tenant_agg: { title: "kept" } } } };
  const scorecards: Record<string, unknown>[] = [];
  const runs = new Map((opts.runs ?? []).map((r) => [String(r.identifier), r]));
  const f = (async (url: string | URL | Request, init?: RequestInit) => {
    const path = String(url).replace(cfg.apiUrl, ""), method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : undefined;
    calls.push({ method, path, body });
    const json = (status: number, data: unknown) => new Response(JSON.stringify(data), { status });
    if (path === "/v1/auth/access_token") return json(200, { accessToken: "t", expiresIn: 10800 });
    const bp = path.match(/^\/v1\/blueprints\/([^/?]+)$/);
    if (bp && method === "GET") return blueprints[bp[1]] ? json(200, { blueprint: blueprints[bp[1]] }) : json(404, {});
    if (bp && method === "PATCH") { blueprints[bp[1]] = { ...blueprints[bp[1]], ...body }; return json(200, {}); }
    if (path === "/v1/blueprints" && method === "POST") { blueprints[String(body!.identifier)] = body!; return json(201, {}); }
    if (path === "/v1/blueprints/githubPullRequest/scorecards" && method === "GET") return json(200, { scorecards });
    if (path === "/v1/blueprints/githubPullRequest/scorecards" && method === "POST") { scorecards.push(body!); return json(201, {}); }
    if (path.startsWith("/v1/blueprints/sf_skill_run/entities?upsert")) {
      const why = opts.refuse?.(body!) ?? null;
      if (why) return json(422, { message: why });
      const prev = runs.get(String(body!.identifier)) ?? {};
      runs.set(String(body!.identifier), { ...prev, ...body, properties: { ...(prev.properties as object ?? {}), ...(body!.properties as object) } });
      return json(200, {});
    }
    if (path === "/v1/blueprints/sf_skill_run/entities/search") {
      const rules = ((body!.query as { rules: { property: string; operator: string; value: unknown }[] }).rules);
      const hit = [...runs.values()].filter((e) => rules.every((r) => { const v = (e.properties as Record<string, unknown>)[r.property]; return r.operator === "=" ? v === r.value : v !== r.value; }));
      return json(200, { entities: hit });
    }
    if (path === "/v1/workflows/runs/wfr_1") return json(200, { workflowRun: { createdBy: "user_A" } });
    if (path === "/v1/workflows/runs/wfr_unknown") return json(404, {});
    if (path === "/v1/users") return json(200, { users: [{ id: "user_A", email: "a@b.c" }, { id: "user_B", email: "x@y.z" }] });
    return json(404, { message: `unhandled ${method} ${path}` });
  }) as typeof fetch;
  return { f, calls, blueprints, scorecards, runs };
}

const base = { runId: "r1", slug: "code-review-runner", version: 2, manifestHash: "h", status: "succeeded", checksPassed: 6, checksTotal: 6, durationMs: 1000, finishedAt: "2026-10-24T03:00:00.000Z", factoryUrl: "https://f/runs/r1", portRunId: "wfr_1", repository: "giri-skills", pr: 164, headSha: "new", prUrl: "https://github.com/o/giri-skills/pull/164", requestedBy: "a@b.c" };

test("WP6 run → PR link: Ocean's PR id (<repo>-pr-<n>), head flag true on record; gate = aggregation over head reviews + scorecard on sf_ data only", () => {
  assert.equal(prEntityId("giri-skills", 164), "giri-skills-pr-164");
  const e = runEntity(base);
  assert.equal(e.relations.pull_request, "giri-skills-pr-164"); assert.equal(e.properties.sf_is_head_review, true);
  assert.equal(runEntity({ ...base, pr: null, repository: null }).properties.sf_is_head_review, null);
  assert.equal(SKILL_RUN_BLUEPRINT.relations.pull_request.target, "githubPullRequest");
  const agg = PR_REVIEW_AGGREGATION.sf_passing_head_reviews;
  assert.equal(agg.target, "sf_skill_run");
  assert.deepEqual(agg.query.rules.map((r) => r.property), ["sf_status", "sf_skill_slug", "sf_is_head_review"]);
  assert.deepEqual(PR_REVIEW_GATE_SCORECARD.rules[0].query.conditions[0], { property: "sf_passing_head_reviews", operator: ">", value: 0 });
  assert.equal(PR_REVIEW_GATE_SCORECARD.rules[0].identifier, "has_passing_review_run");
});

test("WP6 record: creates aggregation (keeping the tenant's) + gate once; supersedes the PR's earlier head only within the same repo", async () => {
  const p = fake({ runs: [
    { identifier: "run_old", properties: { sf_pr_number: 164, sf_is_head_review: true, sf_head_sha: "old" }, relations: { target: "giri-skills" } },
    { identifier: "run_other_repo", properties: { sf_pr_number: 164, sf_is_head_review: true, sf_head_sha: "zzz" }, relations: { target: "other-repo" } },
  ] });
  const c = new PortClient(cfg, p.f);
  const r = await recordRunInPort(c, base);
  assert.equal(r.identifier, "run_r1"); assert.equal(r.note, undefined);
  const agg = p.blueprints.githubPullRequest.aggregationProperties as Record<string, unknown>;
  assert.ok("sf_passing_head_reviews" in agg && "tenant_agg" in agg, "aggregation added, tenant's kept");
  assert.equal(p.scorecards.length, 1); assert.equal((p.scorecards[0] as { identifier: string }).identifier, "pr_review_gate");
  assert.equal((p.runs.get("run_old")!.properties as Record<string, unknown>).sf_is_head_review, false, "earlier head superseded");
  assert.equal((p.runs.get("run_other_repo")!.properties as Record<string, unknown>).sf_is_head_review, true, "same PR number in another repo untouched");
  assert.equal((p.runs.get("run_r1")!.properties as Record<string, unknown>).sf_is_head_review, true, "the new run stays on head");
  await recordRunInPort(c, { ...base, runId: "r2" });
  assert.equal(p.scorecards.length, 1, "gate not recreated");
  assert.equal(p.calls.filter((x) => x.method === "PATCH" && x.path === "/v1/blueprints/githubPullRequest").length, 1, "aggregation added once");
});

test("WP6 record fallbacks: refused user link is dropped first, then the PR link; each drop is named; evidence never lost", async () => {
  const noUser = fake({ refuse: (b) => ((b.relations as Record<string, unknown>).triggered_by ? "user a@b.c not found" : null) });
  const r1 = await recordRunInPort(new PortClient(cfg, noUser.f), base);
  assert.match(r1.note!, /triggered_by not set: .*not found/); assert.equal((noUser.runs.get("run_r1")!.relations as Record<string, unknown>).pull_request, "giri-skills-pr-164");
  const noPr = fake({ refuse: (b) => ((b.relations as Record<string, unknown>).pull_request ? "related entity missing" : null) });
  const r2 = await recordRunInPort(new PortClient(cfg, noPr.f), base);
  assert.match(r2.note!, /triggered_by and pull_request not set/); assert.ok(noPr.runs.has("run_r1"));
});

test("WP6 synchronize: supersede marks every on-head run of that PR whose commit differs; the new head's runs are kept", async () => {
  const p = fake({ runs: [
    { identifier: "a", properties: { sf_pr_number: 7, sf_is_head_review: true, sf_head_sha: "c1" }, relations: { target: "giri-skills" } },
    { identifier: "b", properties: { sf_pr_number: 7, sf_is_head_review: true, sf_head_sha: "c2" }, relations: { target: "giri-skills" } },
  ] });
  assert.equal(await supersedeHeadReviews(new PortClient(cfg, p.f), "giri-skills", 7, "c2"), 1);
  assert.equal((p.runs.get("a")!.properties as Record<string, unknown>).sf_is_head_review, false);
  assert.equal((p.runs.get("b")!.properties as Record<string, unknown>).sf_is_head_review, true);
});

test("WP6 triggered by: resolved from the workflow run's createdBy through Port's users; unknown → null, never guessed", async () => {
  const p = fake();
  assert.equal(await resolveTriggerEmail(new PortClient(cfg, p.f), "wfr_1"), "a@b.c");
  assert.equal(await resolveTriggerEmail(new PortClient(cfg, p.f), "wfr_unknown"), null);
});
