import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { verifySignature, normalize, matchAutomations, unionChecks, checkRunOutput, type AutomationRow } from "../lib/automations/webhook.ts";

const SHA = "a".repeat(40);
const sign = (body: string, secret: string) => "sha256=" + createHmac("sha256", secret).update(body).digest("hex");

test("signature: valid passes; tampered body, wrong secret, missing or malformed header fail", () => {
  const body = JSON.stringify({ zen: "x" });
  assert.equal(verifySignature(body, sign(body, "s3cret"), "s3cret"), true);
  assert.equal(verifySignature(body + " ", sign(body, "s3cret"), "s3cret"), false);
  assert.equal(verifySignature(body, sign(body, "other"), "s3cret"), false);
  assert.equal(verifySignature(body, null, "s3cret"), false);
  assert.equal(verifySignature(body, "sha1=abc", "s3cret"), false);
  assert.equal(verifySignature(body, sign(body, ""), ""), false);
});

const base = { installation: { id: 77 }, repository: { full_name: "acme/billing", default_branch: "main" } };
test("normalize: PR opened/synchronize act; drafts, closes and other repos' noise are ignored", () => {
  const pr = (action: string, extra = {}) => normalize("pull_request", { ...base, action, pull_request: { number: 12, title: "Add RLS", head: { sha: SHA, repo: { full_name: "acme/billing" } }, base: { repo: { full_name: "acme/billing" } }, ...extra } });
  assert.deepEqual(pr("opened"), { kind: "pull_request", installationId: 77, repo: "acme/billing", sha: SHA, baseSha: null, pr: 12, title: "Add RLS", fromFork: false });
  assert.equal(pr("synchronize")?.kind, "pull_request");
  // the base commit travels with the event (findings checks score the delta against it); a malformed one is dropped, not fatal
  const BASE = "b".repeat(40);
  assert.equal((pr("opened", { base: { sha: BASE, repo: { full_name: "acme/billing" } } }) as { baseSha: string | null }).baseSha, BASE);
  assert.equal((pr("synchronize", { base: { sha: "not-a-sha" } }) as { baseSha: string | null }).baseSha, null);
  // "Re-run" on the check in GitHub's Checks tab (found on the first real PR: the click did nothing)
  const rerun = (extra = {}) => normalize("check_run", { ...base, action: "rerequested", check_run: { head_sha: SHA, pull_requests: [{ number: 3, head: { sha: SHA }, base: { sha: BASE } }], ...extra } });
  assert.deepEqual(rerun(), { kind: "pull_request", installationId: 77, repo: "acme/billing", sha: SHA, baseSha: BASE, pr: 3, title: "", fromFork: false });
  assert.deepEqual(rerun({ pull_requests: [] }), { kind: "push", installationId: 77, repo: "acme/billing", sha: SHA });
  assert.equal(normalize("check_run", { ...base, action: "created", check_run: { head_sha: SHA } }), null);
  assert.equal(rerun({ head_sha: "nope" }), null);
  assert.equal(pr("closed"), null);
  assert.equal(pr("opened", { draft: true }), null);
  assert.equal(normalize("pull_request", { ...base, action: "opened", pull_request: { number: 1, head: { sha: "nope" } } }), null);
  assert.equal(normalize("pull_request", { repository: base.repository, action: "opened" }), null);   // no installation
});

test("normalize: push acts only on the default branch; branch pushes and deletions are ignored; repo changes re-sync", () => {
  assert.deepEqual(normalize("push", { ...base, ref: "refs/heads/main", after: SHA }), { kind: "push", installationId: 77, repo: "acme/billing", sha: SHA });
  assert.equal(normalize("push", { ...base, ref: "refs/heads/feature", after: SHA }), null);
  assert.equal(normalize("push", { ...base, ref: "refs/heads/main", after: SHA, deleted: true }), null);
  assert.deepEqual(normalize("installation_repositories", { installation: { id: 77 }, action: "added" }), { kind: "repos_changed", installationId: 77 });
  assert.equal(normalize("installation", { installation: { id: 77 }, action: "deleted" }), null);
  assert.equal(normalize("issues", { ...base, action: "opened" }), null);
});

const auto = (p: Partial<AutomationRow>): AutomationRow => ({ id: "a", name: "n", trigger: "github.pull_request", repos: [], checks: [], report_to_github: true, enabled: true, created_by: "u", ...p });
test("matching: trigger, enabled and repo scope; union of checks (empty = all)", () => {
  const e = normalize("pull_request", { ...base, action: "opened", pull_request: { number: 1, head: { sha: SHA } } })!;
  const autos = [auto({ id: "1" }), auto({ id: "2", enabled: false }), auto({ id: "3", trigger: "github.push" }), auto({ id: "4", repos: ["acme/other"] }), auto({ id: "5", repos: ["acme/billing"], checks: ["rls"] })];
  assert.deepEqual(matchAutomations(e, autos).map((a) => a.id), ["1", "5"]);
  assert.equal(unionChecks([auto({ checks: ["rls"] }), auto({ checks: [] })]), undefined);
  assert.deepEqual(unionChecks([auto({ checks: ["rls"] }), auto({ checks: ["rls", "tenancy"] })]), ["rls", "tenancy"]);
});

test("check run: failure on any fail/error, neutral on warnings or nothing run, success when all ran checks pass", () => {
  const r = (verdict: string) => ({ check: "x", title: "X | y", verdict, summary: "line1\nline2" });
  assert.equal(checkRunOutput([r("pass"), r("skipped")], "https://u").conclusion, "success");
  assert.equal(checkRunOutput([r("pass"), r("warn")], "https://u").conclusion, "neutral");
  assert.equal(checkRunOutput([r("pass"), r("error")], "https://u").conclusion, "failure");
  assert.equal(checkRunOutput([], "https://u").conclusion, "neutral");
  const o = checkRunOutput([r("fail"), r("pass")], "https://portal/catalog/1");
  assert.equal(o.title, "1 of 2 checks failed");
  assert.match(o.summary, /\| X \\\| y \| ❌ fail \| line1 line2 \|/);
  assert.match(o.summary, /Evidence: https:\/\/portal\/catalog\/1$/);
});
