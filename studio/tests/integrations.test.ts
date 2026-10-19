import { test } from "node:test";
import assert from "node:assert/strict";
import { mapVercel, mapSupabase, supabaseRefs } from "../lib/integrations/map.ts";

// Shapes taken from this workspace's real Vercel and Supabase APIs (Oct 2026); ids shortened where irrelevant.
const NOW = Date.parse("2026-10-19T20:00:00Z");
const day = 86_400_000;

test("vercel: project → service with repo, production URL, last deploy and deploy counts; relations with evidence", () => {
  const projects = [{
    id: "prj_l7q3PfIIcF7PaWPJmmytfiNRxj1Y", name: "giri-skills-studio", framework: "nextjs", updatedAt: NOW - day,
    link: { type: "github", org: "giritharanchockalingam", repo: "giri-skills", productionBranch: "main" },
    targets: { production: { alias: ["giri-skills-studio-git-main-x.vercel.app", "giri-skills-studio.vercel.app"] } },
  }, { id: "prj_none", name: "mf-demo-payload-p1", framework: null }];
  const deploys = new Map([["prj_l7q3PfIIcF7PaWPJmmytfiNRxj1Y", [
    { uid: "dpl_1", created: NOW - 2 * day, readyState: "READY", target: "production", meta: { githubCommitSha: "f".repeat(40) } },
    { uid: "dpl_2", created: NOW - 40 * day, readyState: "READY", target: "production" },
    { uid: "dpl_3", created: NOW - 3 * day, readyState: "ERROR", target: "production" },
    { uid: "dpl_4", created: NOW - 1 * day, readyState: "READY", target: "preview" },
  ]]]);
  const envs = new Map([["prj_l7q3PfIIcF7PaWPJmmytfiNRxj1Y", [
    { key: "NEXT_PUBLIC_SUPABASE_URL", value: "https://ysesfztvcexufoogjgth.supabase.co", type: "plain" },
    { key: "SUPABASE_SERVICE_ROLE_KEY", value: "eyJ…", type: "sensitive" },
  ]]]);
  const { entities, relations } = mapVercel({ slug: "giritharan-chockalingams-projects" }, projects, deploys, envs, NOW);
  const s = entities[0];
  assert.equal(s.kind, "service");
  assert.equal(s.url, "https://vercel.com/giritharan-chockalingams-projects/giri-skills-studio");
  assert.equal(s.properties.production_url, "https://giri-skills-studio.vercel.app", "the -git- alias is skipped");
  assert.equal(s.properties.repo, "giritharanchockalingam/giri-skills");
  assert.deepEqual(s.properties.last_deploy, { state: "READY", at: new Date(NOW - 2 * day).toISOString(), sha: "f".repeat(40) }, "newest production deploy, preview ignored");
  assert.equal(s.properties.deploys_30d, 1);
  assert.equal(s.properties.failed_30d, 1);
  assert.equal((s.properties.prod_deploys as string[]).length, 2, "READY production deploys only");
  assert.deepEqual(relations.map((r) => [r.type, r.to.key, r.evidence]), [
    ["built_from", "giritharanchockalingam/giri-skills", "Vercel Git link giritharanchockalingam/giri-skills (main)"],
    ["uses_database", "ysesfztvcexufoogjgth", "Vercel env NEXT_PUBLIC_SUPABASE_URL → project ysesfztvcexufoogjgth"],
  ]);
  assert.deepEqual(entities[1].properties.last_deploy, null, "no deployments: nothing invented");
  assert.equal(entities[1].properties.repo, null);
});

test("vercel env: only plain *SUPABASE_URL values naming a real project ref are read", () => {
  assert.deepEqual(supabaseRefs([
    { key: "SUPABASE_URL", value: "https://abcdefghijklmnopqrst.supabase.co/", type: "plain" },
    { key: "NEXT_PUBLIC_SUPABASE_URL", value: "https://abcdefghijklmnopqrst.supabase.co", type: "plain" },
    { key: "OTHER_SUPABASE_URL", value: "enc:xyz", type: "encrypted" },
    { key: "DATABASE_URL", value: "https://zzzzzzzzzzzzzzzzzzzz.supabase.co", type: "plain" },
    { key: "SUPABASE_URL", value: "https://evil.example.com", type: "plain" },
  ]), [{ ref: "abcdefghijklmnopqrst", key: "SUPABASE_URL" }]);
});

test("supabase: projects → databases", () => {
  const db = mapSupabase([{ id: "ysesfztvcexufoogjgth", ref: "ysesfztvcexufoogjgth", name: "COPILOT SLM PORTAL", region: "us-east-1", status: "ACTIVE_HEALTHY",
    organization_id: "fltzcjwmtenorahvhlcs", created_at: "2026-03-09T15:13:10.159688Z", database: { version: "17.6.1.063", postgres_engine: "17" } }]);
  assert.deepEqual([db[0].kind, db[0].key, db[0].title, db[0].url, db[0].properties.postgres, db[0].properties.status],
    ["database", "ysesfztvcexufoogjgth", "COPILOT SLM PORTAL", "https://supabase.com/dashboard/project/ysesfztvcexufoogjgth", "17.6.1.063", "ACTIVE_HEALTHY"]);
});

import { readVercel, vercelConfig, supabaseConfig } from "../lib/integrations/fetch.ts";
test("vercel fetch: team slug, paginated projects, per-project deployments and settings; one project's failure is reported, not fatal", async () => {
  const seen: string[] = [];
  const f = (async (url: string, init: RequestInit) => {
    seen.push(url.replace("https://api.vercel.com", ""));
    assert.equal((init.headers as Record<string, string>).Authorization, "Bearer t0k");
    const u = new URL(url);
    const j = (o: unknown, status = 200) => new Response(JSON.stringify(o), { status });
    if (u.pathname === "/v2/teams/team_1") return j({ slug: "acme" });
    if (u.pathname === "/v10/projects") return u.searchParams.get("from") ? j({ projects: [{ id: "p2", name: "two" }], pagination: { next: null } }) : j({ projects: [{ id: "p1", name: "one" }], pagination: { next: 123 } });
    if (u.pathname === "/v6/deployments") return u.searchParams.get("projectId") === "p2" ? j({ error: { message: "Forbidden" } }, 403) : j({ deployments: [{ uid: "d", created: 1, readyState: "READY", target: "production" }] });
    if (u.pathname.endsWith("/env")) return j({ envs: [] });
    return j({}, 404);
  }) as unknown as typeof fetch;
  const r = await readVercel({ token: "t0k", teamId: "team_1" }, f, 100 * 86_400_000);
  assert.equal(r.team.slug, "acme");
  assert.deepEqual(r.projects.map((p) => p.name), ["one", "two"]);
  assert.equal(r.deploys.get("p1")?.length, 1);
  assert.equal(r.deploys.has("p2"), false);
  assert.match(r.problems.join(), /two deployments: .*403 Forbidden/);
  assert.ok(seen.some((s) => s.includes("target=production") && s.includes("teamId=team_1")));
  assert.equal(vercelConfig({}).ok, false);
  assert.deepEqual(vercelConfig({ VERCEL_TOKEN: " x ", VERCEL_TEAM_ID: "team_1" }), { ok: true, token: "x", teamId: "team_1", slug: null });
  assert.equal(supabaseConfig({ SUPABASE_ACCESS_TOKEN: "s" }).ok, true);
});

test("vercel fetch: team lookup refused → still syncs; project list refused → says the token's scope is wrong", async () => {
  const j = (o: unknown, status = 200) => new Response(JSON.stringify(o), { status });
  const ok = (async (url: string) => { const u = new URL(url);
    if (u.pathname.startsWith("/v2/teams")) return j({ error: { message: "You are not authorized" } }, 403);
    if (u.pathname === "/v10/projects") return j({ projects: [{ id: "p1", name: "one" }], pagination: { next: null } });
    return j({ deployments: [], envs: [] }); }) as unknown as typeof fetch;
  const r = await readVercel({ token: "t", teamId: "team_1", slug: "acme" }, ok);
  assert.equal(r.team.slug, "acme");
  assert.equal(r.projects.length, 1);
  const denied = (async () => j({ error: { message: "You are not authorized" } }, 403)) as unknown as typeof fetch;
  await assert.rejects(readVercel({ token: "t", teamId: "team_1" }, denied), /cannot list team team_1's projects \(403\)\. Create the token with Scope set to that team/);
});
