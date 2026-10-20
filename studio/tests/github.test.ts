// GitHub App client + detection. Detection runs on THIS repository's real file list (git ls-files).
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { generateKeyPairSync, createVerify } from "node:crypto";
import { readFileSync } from "node:fs";
import { appJwt, signState, verifyState, githubConfig, paginate, gh, GithubError, userCanAccessInstallation } from "../lib/github/app.ts";
import { detect, defaultOwner } from "../lib/github/detect.ts";
import { profileRepo } from "../lib/github/sync.ts";

test("app JWT is RS256, verifiable with the public key, 9-minute window backdated 60 s", () => {
  const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048, privateKeyEncoding: { type: "pkcs1", format: "pem" }, publicKeyEncoding: { type: "spki", format: "pem" } });
  const jwt = appJwt("12345", privateKey, 1_800_000_000);
  const [h, b, sig] = jwt.split(".");
  const dec = (s: string) => JSON.parse(Buffer.from(s.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString());
  assert.deepEqual(dec(h), { alg: "RS256", typ: "JWT" });
  assert.deepEqual(dec(b), { iat: 1_800_000_000 - 60, exp: 1_800_000_000 + 540, iss: "12345" });
  assert.ok(createVerify("RSA-SHA256").update(`${h}.${b}`).verify(publicKey, Buffer.from(sig.replace(/-/g, "+").replace(/_/g, "/"), "base64")));
});

test("state: round-trips, rejects tampering, other secrets, expiry and future timestamps", () => {
  const s = signState({ w: "ws-1", u: "user-1" }, "secret", 1_000_000);
  assert.deepEqual(verifyState(s, "secret", 1_000_000 + 60_000), { w: "ws-1", u: "user-1" });
  assert.equal(verifyState(s, "other", 1_000_000), null);
  assert.equal(verifyState(s, "secret", 1_000_000 + 16 * 60_000), null);
  assert.equal(verifyState(s, "secret", 1_000_000 - 120_000), null);
  const [body, mac] = s.split(".");
  const forged = Buffer.from(JSON.stringify({ w: "ws-2", u: "user-1", t: 1_000_000 })).toString("base64url");
  assert.equal(verifyState(`${forged}.${mac}`, "secret", 1_000_000), null);
  assert.equal(verifyState(`${body}.`, "secret", 1_000_000), null);
  assert.equal(verifyState("garbage", "secret", 1_000_000), null);
});

test("config: lists exactly the missing variables; unescapes \\n in the key", () => {
  assert.deepEqual((githubConfig({}) as { missing: string[] }).missing, ["GITHUB_APP_ID", "GITHUB_APP_SLUG", "GITHUB_APP_PRIVATE_KEY", "GITHUB_APP_CLIENT_ID", "GITHUB_APP_CLIENT_SECRET"]);
  const r = githubConfig({ GITHUB_APP_ID: "1", GITHUB_APP_SLUG: "s", GITHUB_APP_PRIVATE_KEY: "-----BEGIN-----\\nabc\\n-----END-----", GITHUB_APP_CLIENT_ID: "c", GITHUB_APP_CLIENT_SECRET: "x" });
  assert.ok(r.ok && r.cfg.privateKey === "-----BEGIN-----\nabc\n-----END-----");
});

// HTTP: a recording stand-in for fetch (GitHub itself is exercised live; see HANDOFF)
const fakeFetch = (pages: Record<string, { body: unknown; status?: number; next?: string }>, seen: string[] = []) =>
  (async (url: string, init: RequestInit) => {
    seen.push(`${init.method} ${url} ${(init.headers as Record<string, string>).Authorization}`);
    const p = pages[url];
    if (!p) return new Response(JSON.stringify({ message: "Not Found" }), { status: 404 });
    return new Response(typeof p.body === "string" ? p.body : JSON.stringify(p.body), { status: p.status ?? 200, headers: p.next ? { link: `<${p.next}>; rel="next"` } : {} });
  }) as unknown as typeof fetch;

test("pagination follows Link rel=next and reports truncation at the page cap", async () => {
  const A = "https://api.github.com/x?page=1", B = "https://api.github.com/x?page=2", C = "https://api.github.com/x?page=3";
  const f = fakeFetch({ [A]: { body: [1, 2], next: B }, [B]: { body: [3], next: C }, [C]: { body: [4] } });
  assert.deepEqual(await paginate<number[], number>(A, "Bearer t", (p) => p, 10, f), { items: [1, 2, 3, 4], truncated: false });
  assert.deepEqual(await paginate<number[], number>(A, "Bearer t", (p) => p, 2, f), { items: [1, 2, 3], truncated: true });
  await assert.rejects(gh("/nope", "Bearer t", { fetchImpl: f }), (e: unknown) => e instanceof GithubError && e.status === 404 && /Not Found/.test(e.message));
});

test("ownership proof: an installation the user cannot see is refused", async () => {
  const seen: string[] = [];
  const f = fakeFetch({ "https://api.github.com/user/installations?per_page=100": { body: { installations: [{ id: 7 }, { id: 9 }] } } }, seen);
  assert.equal(await userCanAccessInstallation("utok", 9, f), true);
  assert.equal(await userCanAccessInstallation("utok", 8, f), false);
  assert.match(seen[0], /^GET https:\/\/api\.github\.com\/user\/installations\?per_page=100 Bearer utok$/);
});

test("detect: this repository, from its real file list", () => {
  const root = new URL("../..", import.meta.url).pathname;
  const paths = execFileSync("git", ["ls-files"], { cwd: root, encoding: "utf8" }).trim().split("\n");
  const d = detect(paths, { packageJson: readFileSync(new URL("../package.json", import.meta.url), "utf8") });
  const ids = d.stack.map((s) => s.id);
  for (const want of ["nextjs", "supabase", "python", "github-actions", "tests", "agent-skills", "typescript"]) assert.ok(ids.includes(want), `stack has ${want}: ${ids}`);
  const rls = d.applicable.find((a) => a.skill === "build/supabase-schema-rls");
  assert.ok(rls && rls.input?.path === "studio/supabase/migrations", JSON.stringify(rls));
  assert.ok(d.counts.migrations >= 5 && d.counts.workflows >= 1 && d.counts.tests > 50);
  assert.equal(new Set(d.applicable.map((a) => a.skill)).size, d.applicable.length, "one entry per skill");
  assert.ok(d.applicable.every((a) => a.evidence.length > 0), "every match shows its evidence");
});

test("detect: empty repo and a repo with no tests or CI", () => {
  assert.deepEqual(detect([]), { stack: [], applicable: [], counts: { files: 0, tests: 0, migrations: 0, workflows: 0 } });
  const d = detect(["next.config.js", "app/page.tsx", "app/layout.tsx", "lib/a.ts", "lib/b.ts", "README.md", "node_modules/x/test/a.test.js"]);
  const skills = d.applicable.map((a) => a.skill);
  assert.ok(skills.includes("build/test-strategy-tdd") && skills.includes("build/ci-cd-vercel-github"));
  assert.equal(d.counts.tests, 0, "node_modules is ignored");
});

test("detect: CI is matched on a gap, and general skills are not specific matches", async () => {
  const { specificMatches } = await import("../lib/github/detect.ts");
  const withCi = detect(["vercel.json", ".github/workflows/ci.yml", "a.test.ts", "b.ts", "c.ts", "d.ts", "e.ts"]);
  assert.ok(!withCi.applicable.some((a) => a.skill === "build/ci-cd-vercel-github"), "a repository with CI needs no CI skill");
  assert.deepEqual(specificMatches(withCi.applicable).map((a) => a.skill), []);
  const noCi = detect(["vercel.json", "a.test.ts", "b.ts"]);
  assert.ok(noCi.applicable.some((a) => a.skill === "build/ci-cd-vercel-github"));
});

test("CODEOWNERS: the last catch-all rule wins; comments and path rules ignored", () => {
  assert.equal(defaultOwner("# owners\n*  @acme/platform\n/docs/ @acme/docs\n* @acme/core @lead # final\n"), "@acme/core @lead");
  assert.equal(defaultOwner("/src/ @a"), null);
  assert.equal(defaultOwner(null), null);
});

test("profileRepo: tree + package.json + CODEOWNERS become one catalog record with evidence", async () => {
  const repo = { id: 42, name: "billing", full_name: "acme/billing", html_url: "https://github.com/acme/billing", private: true, archived: false, fork: false,
    default_branch: "main", language: "TypeScript", topics: ["payments"], description: "Billing app", pushed_at: "2026-10-01T00:00:00Z", owner: { login: "acme" } };
  const seen: string[] = [];
  const f = fakeFetch({
    "https://api.github.com/repos/acme/billing/git/trees/main?recursive=1": { body: { truncated: false, tree: [
      { path: "package.json", type: "blob" }, { path: "next.config.mjs", type: "blob" }, { path: ".github/CODEOWNERS", type: "blob" },
      { path: "supabase/migrations/0001_init.sql", type: "blob" }, { path: "app/page.tsx", type: "blob" }, { path: "supabase", type: "tree" }] } },
    "https://api.github.com/repos/acme/billing/contents/package.json": { body: JSON.stringify({ dependencies: { next: "15", "@supabase/supabase-js": "2", openai: "4" } }) },
    "https://api.github.com/repos/acme/billing/contents/.github/CODEOWNERS": { body: "* @acme/payments\n" },
  }, seen);
  const p = await profileRepo("itok", repo, f);
  assert.equal(p.key, "acme/billing"); assert.equal(p.owner, "@acme/payments"); assert.equal(p.external_id, "42");
  const props = p.properties as { stack: { id: string }[]; applicable: { skill: string }[]; visibility: string; owner_source: string };
  assert.deepEqual(props.stack.map((x) => x.id).sort(), ["llm", "nextjs", "supabase"]);
  assert.ok(props.applicable.some((a) => a.skill === "build/supabase-schema-rls") && props.applicable.some((a) => a.skill === "ai-platform/guardrails-config"));
  assert.equal(props.visibility, "private"); assert.equal(props.owner_source, ".github/CODEOWNERS");
  assert.ok(seen.every((x) => x.endsWith("Bearer itok")), "only the installation token is used");
  assert.ok(!seen.some((x) => x.includes("requirements.txt")), "absent files are not fetched");
});

test("detect: paths from someone's own machine are dropped at ingest, never shown as evidence", async () => {
  const { isLocalArtifact } = await import("../lib/github/detect.ts");
  const leak = "hms/apps/web/chmod +x /Users/alex/Desktop/hms/deploy.sh/google-cloud-sdk/bin/setup.py";
  for (const p of [leak, "run /home/bob/notes.md", "/home/bob/x", "C:\\Users\\carol\\a.txt", "docs/C:/Users/dave/b.md"]) assert.ok(isLocalArtifact(p), p);
  for (const p of ["src/users/list.ts", "app/Users.tsx", "home/page.tsx", "lib/homepage/x.ts", "x/home/bob/notes.md"]) assert.ok(!isLocalArtifact(p), p);
  const d = detect([leak, "next.config.js", "app/page.tsx"]);
  assert.ok(JSON.stringify(d).indexOf("/Users/") === -1, "no local path anywhere in the detection");
  assert.equal(d.counts.files, 2);
});
