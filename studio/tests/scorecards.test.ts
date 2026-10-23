// Scorecard verdicts are read from REAL skill output: each test runs the library skill (scripts/run_skill.py) on this
// repository's own files, then scores what it wrote.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CHECKS, bound, checksFor, commonDir, errorLine, brownfield, brownfieldVerdict, observabilityMissing, parseCsv, MAX_FILES, type TreeFile } from "../lib/scorecards/checks.ts";
import { mkdirSync, writeFileSync } from "node:fs";

const ROOT = new URL("../..", import.meta.url).pathname;
const check = (id: string) => CHECKS.find((c) => c.id === id)!;
/** Every temp folder a test makes is removed when the file finishes (a full studio copy is >1 GB with node_modules). */
const temps: string[] = [];
const temp = (prefix: string) => { const d = mkdtempSync(join(tmpdir(), prefix)); temps.push(d); return d; };
after(() => { for (const d of temps) rmSync(d, { recursive: true, force: true }); });
/** The files the observability check sends the skill (the same set CHECKS.observability.select picks in production). */
function observabilitySeed(): string {
  const seed = temp("obs-seed-");
  for (const rel of ["package.json", ".env.example", "lib/logger.ts", "lib/logger", "app/api/health", "ops/alerts.yml", "ops/alerts.yaml", "docs/observability.md"]) {
    const src = join(ROOT, "studio", rel);
    if (existsSync(src)) cpSync(src, join(seed, rel), { recursive: true });
  }
  return seed;
}
function runSkill(skill: string, inputs: Record<string, string>) {
  const out = temp("sc-");
  const args = ["scripts/run_skill.py", skill, "--provider", "none", "--out", out, ...Object.entries(inputs).flatMap(([k, v]) => ["--input", `${k}=${v}`])];
  const r = spawnSync("python3", args, { cwd: ROOT, encoding: "utf8" });
  const outs = readdirSync(out).filter((f) => statSync(join(out, f)).isFile()).map((f) => ({ path: f, content_text: readFileSync(join(out, f), "utf8") }));
  return { outs, status: r.status === 0 ? "succeeded" : "failed" };
}

test("rls: real lint output of this repo's migrations → pass with counts", () => {
  const r = runSkill("build/supabase-schema-rls", { migrations: "studio/supabase/migrations" });
  assert.deepEqual(check("rls").score(r.outs, r.status), { verdict: "pass", summary: "0 error(s), 0 warning(s) in the migrations", findings: 0 });
});

test("tenancy: real audit with the detected key → verdict follows the table count", () => {
  const r = runSkill("build/multi-tenant-saas-patterns", { migrations: "studio/supabase/migrations", tenant_column: "auto" });
  const s = check("tenancy").score(r.outs, r.status);
  const m = s.summary.match(/^(\d+) of \d+ tables need tenancy fixes \(key: workspace_id\)$/);
  assert.ok(m, s.summary);
  assert.equal(s.verdict, Number(m![1]) > 0 ? "fail" : "pass");
});

test("nextjs: real conventions lint of the studio app → verdict follows high-severity findings", () => {
  const r = runSkill("build/nextjs-enterprise-conventions", { target: "studio" });
  const s = check("nextjs").score(r.outs, r.status);
  assert.ok(["fail", "warn", "pass"].includes(s.verdict));
  assert.match(s.summary, /^\d+ high, \d+ medium finding\(s\) in \d+ file\(s\)$/);
  assert.equal(s.verdict === "fail", /^[1-9]\d* high/.test(s.summary));
});

test("observability: real dry-run install report → missing pieces decide, customised files are in place", () => {
  // this repository's studio app (pieces installed, two customised)
  const here = runSkill("build/observability-setup", { seed: observabilitySeed(), target: join(temp("obs-"), "repo"), dry_run: "true" });
  const s = check("observability").score(here.outs, here.status);
  assert.equal(s.verdict, "pass", s.summary);
  assert.match(s.summary, /^logging, health checks, alerts and runbook in place \(\d+ customised from the standard\)$/);
  // an app with none of it (the skill's own new-mode fixture repo)
  const bare = runSkill("build/observability-setup", { target: join(temp("obs-"), "repo"), dry_run: "true" });
  const b = check("observability").score(bare.outs, bare.status);
  assert.ok(b.verdict === "fail" && /^\d+ piece\(s\) missing: /.test(b.summary), JSON.stringify(b));
});

test("outputs without a summary are an error, never a pass", () => {
  for (const c of CHECKS) assert.equal(c.score([{ path: c.primary, content_text: "unexpected" }], "succeeded").verdict, "error", c.id);
});

test("selection on this repo's real tree: migrations folder, Next.js app scoped to its folder", () => {
  const files: TreeFile[] = execFileSync("git", ["ls-files", "-s"], { cwd: ROOT, encoding: "utf8" }).trim().split("\n")
    .map((l) => { const [meta, path] = l.split("\t"); return { path, sha: meta.split(" ")[1], size: 1000 }; })
    .concat([{ path: "studio/next.config.mjs", sha: "x", size: 10 }]);
  const mig = check("rls").select(files)[0];
  assert.equal(mig.strip, "studio/supabase/migrations");
  assert.ok(mig.files.length >= 5 && mig.files.every((f) => f.path.endsWith(".sql")));
  const nx = check("nextjs").select(files)[0];
  assert.equal(nx.strip, "studio");
  assert.ok(nx.files.length > 20 && nx.files.every((f) => f.path.startsWith("studio/") && !/\.test\./.test(f.path)));
  const ids = checksFor({ stackIds: ["nextjs", "supabase"], counts: { migrations: 7, files: 900 } }).map((c) => c.id);
  assert.deepEqual(ids, ["rls", "tenancy", "nextjs", "observability"]);
  assert.deepEqual(checksFor({ stackIds: ["python"], counts: { migrations: 0, files: 10 } }), []);
});

test("bound: caps files and bytes, and says so", () => {
  const many = Array.from({ length: MAX_FILES + 5 }, (_, i) => ({ path: `f${String(i).padStart(4, "0")}.ts`, sha: "s", size: 10 }));
  const b = bound(many);
  assert.equal(b.files.length, MAX_FILES); assert.equal(b.partial, true);
  assert.deepEqual(bound([{ path: "a", sha: "s", size: 10 }]), { files: [{ path: "a", sha: "s", size: 10 }], partial: false });
  assert.equal(commonDir(["a/b/c.sql", "a/b/d/e.sql"]), "a/b");
});

const CSV_HEAD = "rule,file,line,snippet,severity,status\n";
test("brownfield: the PR delta keys on (rule, file, normalised snippet) like lint_conventions --baseline; line moves are known", () => {
  const base = CSV_HEAD
    + 'NX1,components/A.tsx,10,"supabase.from(\'orders\')",high,new\n'
    + 'NX2,lib/x.ts,3,"console.log(  a,   b )",medium,new\n'
    + 'NX2,lib/x.ts,4,"console.log(  a,   b )",medium,new\n'
    + 'NX5,lib/gone.ts,1,sql`select 1`,high,new\n';
  const head = CSV_HEAD
    + 'NX1,components/A.tsx,42,"supabase.from(\'orders\')",high,new\n'     // moved: known
    + 'NX2,lib/x.ts,3,"console.log( a, b )",medium,new\n'                  // whitespace runs collapsed (norm_snippet): known
    + 'NX2,lib/x.ts,9,"  console.log( a,  b ) ",medium,new\n'               // second identical snippet: the base had two → known
    + 'NX2,lib/x.ts,12,"console.log( a, b )",medium,new\n'                  // a third: new (one base row matches one finding)
    + 'NX4,app/api/r/route.js,5,process.env.SUPABASE_SERVICE_ROLE_KEY,high,new\n'   // new high
    + '# comment,x,1,y,high,new\n';
  const d = brownfield(head, base);
  assert.deepEqual(d, { new: 2, known: 3, newHigh: 1, resolved: 1, total: 5, newFindings: ["NX2 lib/x.ts:12", "NX4 app/api/r/route.js:5"] });
  assert.deepEqual(brownfieldVerdict(d, "b".repeat(40)), { verdict: "fail", summary: "1 new high finding(s) against base bbbbbbb (3 known, 1 new medium, 1 resolved)", findings: 5 });
  // 77 pre-existing high findings and nothing added: pass, every one of them known
  const debt = CSV_HEAD + Array.from({ length: 77 }, (_, i) => `NX1,components/C${i}.tsx,${i},"createClient()",high,new\n`).join("");
  const same = brownfield(debt, debt);
  assert.deepEqual(brownfieldVerdict(same, "abc1234" + "0".repeat(33)), { verdict: "pass", summary: "0 new high finding(s) against base abc1234 (77 known)", findings: 77 });
  // a new medium only warns; an empty base makes everything new; a header-only CSV is zero findings
  assert.equal(brownfieldVerdict(brownfield(CSV_HEAD + "NX2,a.ts,1,console.log(1),medium,new\n", debt), "c".repeat(40)).verdict, "warn");
  assert.equal(brownfield(debt, "").newHigh, 77);
  assert.deepEqual(brownfield(CSV_HEAD, CSV_HEAD), { new: 0, known: 0, newHigh: 0, resolved: 0, total: 0, newFindings: [] });
  assert.deepEqual(parseCsv('a,b\r\n1,"x, ""y"""\r\n'), [{ a: "1", b: 'x, "y"' }]);
  assert.equal(check("nextjs").findings, "findings.csv");
  for (const id of ["rls", "tenancy", "observability"]) assert.equal(check(id).findings, undefined, id);
});

test("brownfield: REAL lint of a base tree and a head tree → only the head's added high finding is new", () => {
  const root = temp("bf-");
  const write = (rel: string, body: string) => { mkdirSync(join(root, rel, ".."), { recursive: true }); writeFileSync(join(root, rel), body); };
  for (const t of ["base", "head"]) {
    write(`${t}/components/Old.tsx`, "export function Old() {\n  console.log('debt');\n  return supabase.from('t').select('*');\n}\n");   // NX2 + NX1: pre-existing debt
    write(`${t}/package.json`, "{}");
  }
  write("head/components/Old.tsx", "// a comment line moves the debt down one line\nexport function Old() {\n  console.log('debt');\n  return supabase.from('t').select('*');\n}\n");
  write("head/app/api/export/route.js", "const sql = require('x');\nexport async function GET() { return sql`select 1`; }\n");   // NX5: new high
  const b = runSkill("build/nextjs-enterprise-conventions", { target: join(root, "base") });
  const h = runSkill("build/nextjs-enterprise-conventions", { target: join(root, "head") });
  const csv = (r: { outs: { path: string; content_text: string }[] }) => r.outs.find((o) => o.path === "findings.csv")!.content_text;
  const d = brownfield(csv(h), csv(b));
  assert.deepEqual({ new: d.new, known: d.known, newHigh: d.newHigh, resolved: d.resolved }, { new: 1, known: 2, newHigh: 1, resolved: 0 });
  assert.match(d.newFindings[0], /^NX5 app\/api\/export\/route\.js:2$/);
  // the absolute verdict on the head would fail on the base's own debt; the delta fails on the one new high finding only
  assert.equal(check("nextjs").score(b.outs, b.status).verdict, "fail");
  assert.deepEqual(brownfield(csv(h), csv(h)).newHigh, 0);
});

test("observability: a JavaScript app's logger and routes are selected (install.py's sibling extensions), the context helper is not a capability", () => {
  const files = (paths: string[]): TreeFile[] => paths.map((p) => ({ path: p, sha: p, size: 10 }));
  const sel = (paths: string[]) => check("observability").select(files(paths))[0].files.map((f) => f.path);
  assert.deepEqual(sel(["package.json", "jsconfig.json", "lib/logger.js", "lib/logger/context.js", "lib/logger.d.ts", "app/api/health/route.js", "ops/alerts.yaml", "docs/observability.md", "lib/other.js", "node_modules/lib/logger.js"]),
    ["package.json", "jsconfig.json", "lib/logger.js", "lib/logger/context.js", "app/api/health/route.js", "ops/alerts.yaml", "docs/observability.md"]);
  for (const ext of ["ts", "tsx", "js", "jsx", "mjs", "cjs"]) assert.deepEqual(sel([`lib/logger.${ext}`, `lib/logger/context.${ext}`]), [`lib/logger.${ext}`, `lib/logger/context.${ext}`], ext);
  assert.deepEqual(sel(["web/next.config.js", "web/lib/logger.js", "lib/logger.js", "web/tsconfig.json"]), ["web/lib/logger.js", "web/tsconfig.json"]);   // monorepo: the app folder
  assert.deepEqual(observabilityMissing(["lib/logger/context.js", "ops/alerts.yaml"]), ["ops/alerts.yaml"]);
  assert.deepEqual(observabilityMissing(["lib/logger.ts", "lib/logger/context.ts"]), ["lib/logger.ts", "lib/logger/context.ts"]);
  // REAL dry run on a JavaScript seed with its own logger (no context helper), health route, alerts and runbook → in place
  const seed = temp("obs-js-");
  const write = (rel: string, body: string) => { mkdirSync(join(seed, rel, ".."), { recursive: true }); writeFileSync(join(seed, rel), body); };
  write("package.json", "{}"); write("jsconfig.json", "{}");
  write("lib/logger.js", "module.exports = { info() {}, error() {} };\n");
  write("app/api/health/route.js", "export const dynamic = 'force-dynamic';\nexport async function GET() { return Response.json({ ok: true, ts: new Date().toISOString(), sha: '' }, { headers: { 'Cache-Control': 'no-store' } }); }\n");
  write("app/api/health/deep/route.js", "export async function GET() { return new Response('ok'); }\n");
  write("ops/alerts.yaml", "rules: []\n"); write("docs/observability.md", "# SLOs\n"); write(".env.example", "LOG_LEVEL=info\n");
  const r = runSkill("build/observability-setup", { seed, target: join(temp("obs-"), "repo"), dry_run: "true" });
  const s = check("observability").score(r.outs, r.status);
  assert.equal(s.verdict, "pass", s.summary);
  assert.match(JSON.parse(r.outs.find((o) => o.path === "install-report.json")!.content_text).written.join(","), /^lib\/logger\/context\.js$/);   // the installer still proposes the helper
});

test("errorLine: the skill's own last error, without runtime paths", () => {
  assert.equal(errorLine("lint: start\nerror: no .ts/.tsx files under /tmp/sf/abc/inputs/target\n"), "no .ts/.tsx files under target");
  assert.equal(errorLine("all good"), null);
  assert.equal(errorLine(null), null);
});
