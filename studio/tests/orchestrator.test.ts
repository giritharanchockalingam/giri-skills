// Workflow orchestrator I/O paths: webhook intake (signature, de-duplication, scheduling) and event processing
// (check runs, recorded runs, verdict → conclusion, failure handling). GitHub and the runtime are injected fakes;
// the database is an in-memory query builder with supabase-js semantics.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import type { SupabaseClient } from "@supabase/supabase-js";
import { receiveWebhook, type ReceiveDeps } from "../lib/automations/receive.ts";
import { processEvent, type ProcessDeps } from "../lib/automations/process.ts";
import type { NormEvent } from "../lib/automations/webhook.ts";
import { FakeDb } from "./support/fake-supabase.ts";

const WS = "11111111-1111-4111-8111-111111111111";
const USER = "22222222-2222-4222-8222-222222222222";
const SECRET = "test-webhook-secret";
const SHA = "a".repeat(40);
const INST = 4242;
const REPO = "acme/app";

const seed = (extra: Record<string, Record<string, unknown>[]> = {}) => new FakeDb({
  sf_github_installations: [{ workspace_id: WS, installation_id: INST, verified_by: USER, suspended_at: null }],
  sf_catalog_entities: [{ id: "ent-1", workspace_id: WS, kind: "repository", key: REPO }],
  ...extra,
});
const auto = (o: Record<string, unknown> = {}) => ({ id: "auto-1", workspace_id: WS, name: "Pull request gate", trigger: "github.pull_request", repos: [], checks: [], report_to_github: true, enabled: true, created_by: USER, ...o });

/* ---------------- intake ---------------- */
const sign = (raw: string, secret = SECRET) => "sha256=" + createHmac("sha256", secret).update(raw).digest("hex");
const prPayload = JSON.stringify({ action: "opened", installation: { id: INST }, repository: { full_name: REPO, default_branch: "main" },
  pull_request: { number: 7, title: "t", draft: false, head: { sha: SHA, repo: { full_name: REPO } }, base: { repo: { full_name: REPO } } } });
const headers = (raw: string, event = "pull_request", delivery = "d-1", sig = sign(raw)) =>
  new Headers({ "x-github-event": event, "x-github-delivery": delivery, "x-hub-signature-256": sig });
function intake(db: FakeDb, o: Partial<ReceiveDeps> = {}) {
  const scheduled: { e: NormEvent; delivery: string }[] = [];
  const deps: ReceiveDeps = { secret: SECRET, adminReady: true, adminMissing: "admin missing", sb: () => db as unknown as SupabaseClient,
    schedule: (e, delivery) => scheduled.push({ e, delivery }), ...o };
  return { deps, scheduled };
}

test("intake: unsigned, wrongly signed or secret-less requests are rejected with 401", async () => {
  const db = seed(); const { deps, scheduled } = intake(db);
  assert.equal((await receiveWebhook(prPayload, headers(prPayload, "pull_request", "d", "sha256=00"), deps)).status, 401);
  assert.equal((await receiveWebhook(prPayload, headers(prPayload, "pull_request", "d", sign(prPayload, "other")), deps)).status, 401);
  const noSecret = await receiveWebhook(prPayload, headers(prPayload), { ...deps, secret: "" });
  assert.equal(noSecret.status, 401);
  assert.match(JSON.stringify(noSecret.body), /GITHUB_WEBHOOK_SECRET is not set/);
  assert.equal(scheduled.length, 0);
  assert.equal(db.rows("sf_github_deliveries").length, 0);
});

test("intake: ping answers 200; missing admin client is 503 and stores nothing", async () => {
  const db = seed(); const { deps } = intake(db, { adminReady: false });
  assert.deepEqual((await receiveWebhook("{}", headers("{}", "ping"), deps)).body, { ok: true, pong: true });
  const r = await receiveWebhook(prPayload, headers(prPayload), deps);
  assert.equal(r.status, 503);
  assert.equal(db.rows("sf_github_deliveries").length, 0);
});

test("intake: events we don't act on, and unlinked installations, are acknowledged and not recorded", async () => {
  const db = seed(); const { deps, scheduled } = intake(db);
  const issue = JSON.stringify({ action: "opened", installation: { id: INST }, repository: { full_name: REPO } });
  assert.deepEqual((await receiveWebhook(issue, headers(issue, "issues"), deps)).body, { ok: true, ignored: "issues" });
  const other = prPayload.replace(String(INST), "9999");
  assert.equal((await receiveWebhook(other, headers(other), deps)).body.ignored, "installation not linked to a workspace");
  assert.equal(scheduled.length, 0);
  assert.equal(db.rows("sf_github_deliveries").length, 0);
});

test("intake: a new delivery is recorded (workspace-scoped) and scheduled once; a redelivery is a no-op", async () => {
  const db = seed(); const { deps, scheduled } = intake(db);
  const first = await receiveWebhook(prPayload, headers(prPayload, "pull_request", "d-42"), deps);
  assert.equal(first.status, 202);
  assert.deepEqual(first.body, { ok: true, accepted: "pull_request" });
  const again = await receiveWebhook(prPayload, headers(prPayload, "pull_request", "d-42"), deps);
  assert.equal(again.status, 200);
  assert.deepEqual(again.body, { ok: true, duplicate: "d-42" });
  assert.equal(scheduled.length, 1);
  assert.equal(scheduled[0].delivery, "d-42");
  assert.deepEqual(db.rows("sf_github_deliveries").map((r) => [r.delivery_id, r.workspace_id, r.event]), [["d-42", WS, "pull_request"]]);
});

test("intake: a database failure is a 500 (GitHub retries) and nothing is scheduled", async () => {
  const db = seed(); db.failNext.sf_github_deliveries = "connection reset";
  const { deps, scheduled } = intake(db);
  const r = await receiveWebhook(prPayload, headers(prPayload), deps);
  assert.equal(r.status, 500);
  assert.match(JSON.stringify(r.body), /connection reset/);
  assert.equal(scheduled.length, 0);
});

/* ---------------- processing ---------------- */
type Verdict = "pass" | "warn" | "fail" | "error" | "skipped";
function harness(db: FakeDb, o: { verdicts?: Record<string, Verdict>; scoreThrows?: string; scoreNotOk?: string; configOk?: boolean; checkCreateFails?: boolean } = {}) {
  const calls = { created: [] as unknown[], completed: [] as { id: number; conclusion: string; title: string; summary: string }[], scored: [] as unknown[], synced: 0, profiled: 0 };
  const verdicts = o.verdicts ?? { rls: "pass", tenancy: "pass" };
  const deps: ProcessDeps = {
    sb: db as unknown as SupabaseClient,
    config: () => (o.configOk === false ? { ok: false, missing: ["GITHUB_APP_ID"] } : { ok: true, cfg: { appId: "1", slug: "s", privateKey: "k", clientId: "c", clientSecret: "x", webhookSecret: SECRET } }),
    installationToken: async () => "inst-token",
    getRepo: (async () => ({ full_name: REPO })) as unknown as ProcessDeps["getRepo"],
    profileRepo: (async () => { calls.profiled++; return { key: REPO, name: "app", url: "https://github.com/acme/app" }; }) as unknown as ProcessDeps["profileRepo"],
    syncWorkspace: (async () => { calls.synced++; return { ok: true, message: "3 repositories", repos: 3, archived: 0, errors: [] }; }) as ProcessDeps["syncWorkspace"],
    scoreEntity: (async (_sb, _ws, _u, entityId, opts) => {
      calls.scored.push({ entityId, ...opts });
      if (o.scoreThrows) throw new Error(o.scoreThrows);
      if (o.scoreNotOk) return { ok: false, entity: REPO, message: o.scoreNotOk, results: [] };
      return { ok: true, entity: REPO, message: "", sha: SHA, results: Object.entries(verdicts).map(([check, verdict]) => ({ check, title: check.toUpperCase(), verdict, summary: `${check} ${verdict}` })) };
    }) as ProcessDeps["scoreEntity"],
    createCheckRun: (async (_t, _r, b) => { if (o.checkCreateFails) throw new Error("403 Resource not accessible"); calls.created.push(b); return { id: 100 + calls.created.length, html_url: `https://github.com/${REPO}/runs/${100 + calls.created.length}` }; }) as ProcessDeps["createCheckRun"],
    completeCheckRun: (async (_t, _r, id, b) => { calls.completed.push({ id, ...b }); }) as ProcessDeps["completeCheckRun"],
  };
  return { deps, calls };
}
const prEvent: NormEvent = { kind: "pull_request", installationId: INST, repo: REPO, sha: SHA, pr: 7, title: "t", fromFork: false };
const pushEvent: NormEvent = { kind: "push", installationId: INST, repo: REPO, sha: SHA };
const ORIGIN = "https://studio.example";

test("process: a passing pull request gets a success Check Run, a recorded run, and PR-context results", async () => {
  const db = seed({ sf_automations: [auto()] }); const { deps, calls } = harness(db);
  const r = await processEvent(prEvent, "d-1", ORIGIN, deps);
  assert.match(r.handled, /1 automation\(s\) ran on acme\/app@aaaaaaa/);
  assert.deepEqual(calls.created, [{ name: "Skills Factory: Pull request gate", head_sha: SHA, details_url: `${ORIGIN}/catalog/ent-1`, external_id: "auto-1" }]);
  assert.equal(calls.completed[0].conclusion, "success");
  assert.equal(calls.completed[0].title, "All 2 checks passed");
  const [run] = db.rows("sf_automation_runs");
  assert.equal(run.status, "succeeded");
  assert.equal(run.pr_number, 7);
  assert.equal(run.check_run_url, `https://github.com/${REPO}/runs/101`);
  assert.deepEqual(Object.keys(run.verdicts as object).sort(), ["rls", "tenancy"]);
  assert.deepEqual(calls.scored[0], { entityId: "ent-1", ref: SHA, context: "pull_request", prNumber: 7, checks: undefined, automationRunId: run.id });
});

test("process: a failing check makes the Check Run a failure; a warning alone is neutral", async () => {
  const db1 = seed({ sf_automations: [auto()] }); const h1 = harness(db1, { verdicts: { rls: "pass", nextjs: "fail" } });
  await processEvent(prEvent, "d-1", ORIGIN, h1.deps);
  assert.equal(h1.calls.completed[0].conclusion, "failure");
  assert.equal(h1.calls.completed[0].title, "1 of 2 checks failed");
  assert.match(h1.calls.completed[0].summary, /\| NEXTJS \| ❌ fail \| nextjs fail \|/);
  assert.equal(db1.rows("sf_automation_runs")[0].status, "succeeded"); // the run worked; the code failed

  const db2 = seed({ sf_automations: [auto()] }); const h2 = harness(db2, { verdicts: { observability: "warn" } });
  await processEvent(prEvent, "d-2", ORIGIN, h2.deps);
  assert.equal(h2.calls.completed[0].conclusion, "neutral");
});

test("process: when the scorecard cannot run, the Check Run is neutral and says it is our problem; the run is failed", async () => {
  for (const o of [{ scoreThrows: "runtime timeout" }, { scoreNotOk: "Runtime not available: missing URL" }]) {
    const db = seed({ sf_automations: [auto()] }); const { deps, calls } = harness(db, o);
    const r = await processEvent(prEvent, "d-1", ORIGIN, deps);
    assert.match(r.handled, /failed:/);
    assert.equal(calls.completed[0].conclusion, "neutral");
    assert.match(calls.completed[0].summary, /problem on the Skills Factory side, not a verdict on this code/);
    const [run] = db.rows("sf_automation_runs");
    assert.equal(run.status, "failed");
    assert.match(String(run.error), /runtime timeout|Runtime not available/);
  }
});

test("process: two automations share one scorecard run (union of checks) and each gets its own verdict subset", async () => {
  const db = seed({ sf_automations: [auto({ id: "a-rls", name: "RLS", checks: ["rls"] }), auto({ id: "a-ten", name: "Tenancy", checks: ["tenancy"] })] });
  const { deps, calls } = harness(db);
  await processEvent(prEvent, "d-1", ORIGIN, deps);
  assert.equal(calls.scored.length, 1);
  assert.deepEqual((calls.scored[0] as { checks: string[] }).checks.sort(), ["rls", "tenancy"]);
  assert.equal(calls.completed.length, 2);
  const runs = db.rows("sf_automation_runs");
  assert.deepEqual(runs.map((r) => Object.keys(r.verdicts as object)), [["rls"], ["tenancy"]]);
});

test("process: repo filters, disabled automations, wrong trigger and report_to_github=false are honoured", async () => {
  const db = seed({ sf_automations: [
    auto({ id: "other-repo", repos: ["acme/other"] }), auto({ id: "off", enabled: false }), auto({ id: "on-push", trigger: "github.push" }),
    auto({ id: "silent", name: "Silent", report_to_github: false }),
  ] });
  const { deps, calls } = harness(db);
  await processEvent(prEvent, "d-1", ORIGIN, deps);
  assert.equal(calls.created.length, 0);
  const runs = db.rows("sf_automation_runs");
  assert.deepEqual(runs.map((r) => r.automation_id), ["silent"]);
  assert.equal(runs[0].check_run_url, null);
  assert.equal(runs[0].status, "succeeded");
});

test("process: a push to the default branch re-profiles the repository and scores it as the scorecard (default context)", async () => {
  const db = seed({ sf_automations: [auto({ trigger: "github.push", name: "Keep scorecard current" })] });
  const { deps, calls } = harness(db);
  await processEvent(pushEvent, "d-1", ORIGIN, deps);
  assert.equal(calls.profiled, 1);
  assert.equal((calls.scored[0] as { context: string; prNumber: null }).context, "default");
  assert.equal((calls.scored[0] as { prNumber: null }).prNumber, null);
  assert.match(calls.completed[0].summary, /on the default branch/);
  assert.equal(db.rows("sf_catalog_entities").length, 1); // upserted in place, not duplicated
});

test("process: a push with no automation still keeps the catalog current; repos_changed re-syncs the catalog", async () => {
  const db = seed(); const { deps, calls } = harness(db);
  assert.equal((await processEvent(pushEvent, "d-1", ORIGIN, deps)).handled, "repository re-profiled; no automation");
  assert.equal(calls.profiled, 1);
  assert.equal(calls.scored.length, 0);
  assert.match((await processEvent({ kind: "repos_changed", installationId: INST }, "d-2", ORIGIN, deps)).handled, /catalog re-synced: 3 repositories/);
  assert.equal(calls.synced, 1);
});

test("process: unlinked/suspended installations and an unconfigured App do nothing", async () => {
  const db = seed({ sf_automations: [auto()] });
  db.rows("sf_github_installations")[0].suspended_at = "2026-10-01T00:00:00Z";
  const h = harness(db);
  assert.equal((await processEvent(prEvent, "d-1", ORIGIN, h.deps)).handled, "installation not linked to a workspace");
  assert.equal((await processEvent(prEvent, "d-1", ORIGIN, harness(seed(), { configOk: false }).deps)).handled, "github app not configured");
  assert.equal(h.calls.created.length + h.calls.scored.length, 0);
});

test("process: if GitHub refuses the Check Run, the run is still scored and recorded (no check URL)", async () => {
  const db = seed({ sf_automations: [auto()] }); const { deps, calls } = harness(db, { checkCreateFails: true });
  await processEvent(prEvent, "d-1", ORIGIN, deps);
  assert.equal(calls.scored.length, 1);
  assert.equal(calls.completed.length, 0);
  const [run] = db.rows("sf_automation_runs");
  assert.equal(run.status, "succeeded");
  assert.equal(run.check_run_url, null);
});

test("process: if the run cannot be recorded, its Check Run is closed neutral instead of left spinning", async () => {
  const db = seed({ sf_automations: [auto()] }); db.failNext.sf_automation_runs = "insert denied";
  const { deps, calls } = harness(db);
  assert.equal((await processEvent(prEvent, "d-1", ORIGIN, deps)).handled, "could not record any automation run");
  assert.equal(calls.scored.length, 0);
  assert.deepEqual(calls.completed.map((c) => c.conclusion), ["neutral"]);
});
