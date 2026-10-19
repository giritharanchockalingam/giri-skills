// Scorecard verdicts are read from REAL skill output: each test runs the library skill (scripts/run_skill.py) on this
// repository's own files, then scores what it wrote.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CHECKS, bound, checksFor, commonDir, errorLine, MAX_FILES, type TreeFile } from "../lib/scorecards/checks.ts";

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

test("errorLine: the skill's own last error, without runtime paths", () => {
  assert.equal(errorLine("lint: start\nerror: no .ts/.tsx files under /tmp/sf/abc/inputs/target\n"), "no .ts/.tsx files under target");
  assert.equal(errorLine("all good"), null);
  assert.equal(errorLine(null), null);
});
