// Scorecard verdicts are read from REAL skill output: each test runs the library skill (scripts/run_skill.py) on this
// repository's own files, then scores what it wrote.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CHECKS, bound, checksFor, commonDir, MAX_FILES, type TreeFile } from "../lib/scorecards/checks.ts";

const ROOT = new URL("../..", import.meta.url).pathname;
const check = (id: string) => CHECKS.find((c) => c.id === id)!;
function runSkill(skill: string, inputs: Record<string, string>) {
  const out = mkdtempSync(join(tmpdir(), "sc-"));
  const args = ["scripts/run_skill.py", skill, "--provider", "none", "--out", out, ...Object.entries(inputs).flatMap(([k, v]) => ["--input", `${k}=${v}`])];
  const r = spawnSync("python3", args, { cwd: ROOT, encoding: "utf8" });
  const outs = readdirSync(out).filter((f) => statSync(join(out, f)).isFile()).map((f) => ({ path: f, content_text: readFileSync(join(out, f), "utf8") }));
  return { outs, status: r.status === 0 ? "succeeded" : "failed" };
}

test("rls: real lint output of this repo's migrations → pass with counts", () => {
  const r = runSkill("build/supabase-schema-rls", { migrations: "studio/supabase/migrations" });
  assert.deepEqual(check("rls").score(r.outs, r.status), { verdict: "pass", summary: "0 error(s), 0 warning(s) in the migrations", findings: 0 });
});

test("tenancy: real audit with the detected key → fail with the table count", () => {
  const r = runSkill("build/multi-tenant-saas-patterns", { migrations: "studio/supabase/migrations", tenant_column: "auto" });
  const s = check("tenancy").score(r.outs, r.status);
  assert.equal(s.verdict, "fail");
  assert.match(s.summary, /^\d+ of \d+ tables need tenancy fixes \(key: workspace_id\)$/);
});

test("nextjs: real conventions lint of the studio app → verdict follows high-severity findings", () => {
  const r = runSkill("build/nextjs-enterprise-conventions", { target: "studio" });
  const s = check("nextjs").score(r.outs, r.status);
  assert.ok(["fail", "warn", "pass"].includes(s.verdict));
  assert.match(s.summary, /^\d+ high, \d+ medium finding\(s\) in \d+ file\(s\)$/);
  assert.equal(s.verdict === "fail", /^[1-9]\d* high/.test(s.summary));
});

test("observability: real dry-run install report → missing pieces listed", () => {
  const r = runSkill("build/observability-setup", { seed: "studio", target: join(mkdtempSync(join(tmpdir(), "obs-")), "repo"), dry_run: "true" });
  const s = check("observability").score(r.outs, r.status);
  assert.ok(s.verdict === "fail" && /^\d+ piece\(s\) missing: /.test(s.summary), JSON.stringify(s));
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
