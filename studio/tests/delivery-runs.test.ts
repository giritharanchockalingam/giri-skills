// Delivery runs (docs/DELIVERY-PIPELINES.md, increment 3): the pipelines.json ingest shape, the API input schemas, the
// access rule, the stage reducer, the approval authority and the executor hand-off — all pure, no database.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readPipelines, shapePipeline } from "../lib/pipelines.mjs";
import { applyStage, approvalPost, awaitingStage, canApproveStage, canStartPipeline, deliverCommand, seedStages, type DeliveryRun, type Pipeline } from "../lib/delivery/core.ts";
import { dispatch, dispatchGithubActions, workflowInputs } from "../lib/delivery/dispatch.ts";
import { DeliveryApproveInput, DeliveryStageInput, DeliveryStartInput } from "../lib/validation.ts";

const RAW = {
  name: "feature-delivery", version: "0.1.0", title: "Feature delivery", description: "Brownfield.", mode: "brownfield",
  fits: { stacks: ["nextjs"], request_kinds: ["feature", "fix"] },
  inputs: [{ name: "repo", type: "repo", required: true, from: "catalog repository" }, { name: "request", type: "text", required: true, from: "the request" }, { bad: true }],
  stack_profile: { from: "repo", detect: "scripts/stack_profile.py" },
  stages: [
    { id: "requirements", adlc_stage: "requirements", role: "ai-product-manager", steps: [{ id: "prd", kind: "skill", skill: "build/product-spec-prd", inputs: { request: "$in.request" } }], gate: { kind: "output", step: "prd", file: "prd.md", check: "exists" }, evidence: ["$steps.prd:prd.md"] },
    { id: "architecture", adlc_stage: "architecture", role: "ai-solution-architect", steps: [{ id: "plan", kind: "skill", skill: "build/spec-to-plan" }, { id: "plan-approval", kind: "approval", role: "ai-solution-architect" }], gate: { kind: "approval", step: "plan-approval" } },
    { id: "build", adlc_stage: "build", role: "full-stack-engineer", steps: [{ id: "code", kind: "agent", agent: "claude-code" }], gate: { kind: "exit", step: "code" } },
  ],
  outputs: ["$evidence"],
};
const PIPE = shapePipeline(RAW) as Pipeline;

test("pipelines.json: a template is reduced to name, version, title, description, mode, fits, inputs and stages[{id, adlc_stage, role, steps[{id, kind, skill?}], gate}]", () => {
  assert.deepEqual(Object.keys(PIPE), ["name", "version", "title", "description", "mode", "fits", "inputs", "stages"]);
  assert.deepEqual(PIPE.fits, { stacks: ["nextjs"], request_kinds: ["feature", "fix"] });
  assert.deepEqual(PIPE.inputs.map((i) => i.name), ["repo", "request"], "an input without a name is dropped");
  assert.deepEqual(PIPE.stages.map((s) => [s.id, s.adlc_stage, s.role]), [["requirements", "requirements", "ai-product-manager"], ["architecture", "architecture", "ai-solution-architect"], ["build", "build", "full-stack-engineer"]]);
  assert.deepEqual(PIPE.stages[0].steps, [{ id: "prd", kind: "skill", skill: "build/product-spec-prd" }], "step inputs are the executor's business");
  assert.deepEqual(PIPE.stages[1].steps.map((s) => s.kind), ["skill", "approval"]);
  assert.deepEqual(PIPE.stages[1].gate, { kind: "approval", step: "plan-approval" });
  assert.equal(shapePipeline({ name: "x", stages: [{ id: "a" }] }).mode, "brownfield", "mode defaults to brownfield");
  assert.throws(() => shapePipeline({ name: "Bad Name" }), /invalid name/);
  assert.throws(() => shapePipeline({ name: "x", stages: [{}] }), /stage 0 has no id/);
});

test("pipelines.json: the folder may be missing (empty list); files are read sorted by name", () => {
  assert.deepEqual(readPipelines(join(tmpdir(), "no-such-pipelines-dir")), []);
  const dir = mkdtempSync(join(tmpdir(), "pipelines-"));
  writeFileSync(join(dir, "zeta.json"), JSON.stringify({ ...RAW, name: "zeta" }));
  writeFileSync(join(dir, "alpha.json"), JSON.stringify({ ...RAW, name: "alpha", mode: "greenfield" }));
  writeFileSync(join(dir, "README.md"), "not a template");
  assert.deepEqual(readPipelines(dir).map((p) => [p.name, p.mode]), [["alpha", "greenfield"], ["zeta", "brownfield"]]);
  if (existsSync("data/pipelines.json")) {
    const shipped = JSON.parse(readFileSync("data/pipelines.json", "utf8")) as Pipeline[];
    assert.ok(Array.isArray(shipped));
    for (const p of shipped) { assert.match(p.name, /^[a-z0-9-]+$/); assert.ok(["brownfield", "greenfield"].includes(p.mode)); assert.ok(p.stages.every((s) => s.id && s.role && s.adlc_stage)); }
  }
});

test("API input validation: start, stage and approve schemas", () => {
  const start = DeliveryStartInput.parse({ pipeline: "feature-delivery", repo: "acme/billing", request: " add export " });
  assert.deepEqual(start, { pipeline: "feature-delivery", repo: "acme/billing", ref: "", request: "add export", executor: "github-actions" });
  assert.equal(DeliveryStartInput.parse({ pipeline: "x", repo: "./apps/web", request: "r", executor: "ide" }).repo, "./apps/web", "a checkout path is a valid repo for the IDE");
  assert.ok(!DeliveryStartInput.safeParse({ pipeline: "Feature Delivery", repo: "a/b", request: "r" }).success, "pipeline must be a template name");
  assert.ok(!DeliveryStartInput.safeParse({ pipeline: "x", repo: "a/b", request: "   " }).success, "request is required");
  assert.ok(!DeliveryStartInput.safeParse({ pipeline: "x", repo: "a/b", request: "r", executor: "cloud" }).success, "unknown executor");
  assert.ok(!DeliveryStartInput.safeParse({ pipeline: "x", repo: "a/b", request: "r", ref: "ref with spaces" }).success, "ref is a branch or sha");

  const stage = DeliveryStageInput.parse({ id: "build", status: "succeeded", gate: { kind: "exit", verdict: "pass" }, evidence: [{ path: "report.md", sha256: "a".repeat(64), bytes: 10 }], finished_at: "2026-10-22T10:00:00Z", pr: { number: 7, url: "https://github.com/acme/billing/pull/7" } });
  assert.equal(stage.gate?.verdict, "pass");
  assert.ok(!DeliveryStageInput.safeParse({ id: "build", status: "done" }).success, "stage status is an enum");
  assert.ok(!DeliveryStageInput.safeParse({ id: "build", status: "succeeded", evidence: [{ path: "x", sha256: "abc", bytes: 1 }] }).success, "sha256 must be 64 hex");
  assert.ok(!DeliveryStageInput.safeParse({ id: "build", status: "succeeded", gate: { kind: "exit", verdict: "ok" } }).success, "verdict is pass|fail|pending");
  assert.ok(!DeliveryStageInput.safeParse({ status: "running" }).success, "stage id is required");

  assert.deepEqual(DeliveryApproveInput.parse({ stage_id: "architecture" }), { stage_id: "architecture", note: "" });
  assert.ok(!DeliveryApproveInput.safeParse({ stage_id: "" }).success);
});

test("access rule: admins always; no sf_pipeline_access rows = open; otherwise a listed job role is needed", () => {
  assert.equal(canStartPipeline({ member: "admin", job: [] }, ["ai-solution-architect"]), true);
  assert.equal(canStartPipeline({ member: "consumer", job: [] }, []), true, "open pipeline");
  assert.equal(canStartPipeline({ member: "author", job: [] }, ["ai-solution-architect"]), false, "authors are not builders here: the role decides");
  assert.equal(canStartPipeline({ member: "consumer", job: ["ai-solution-architect"] }, ["ai-solution-architect", "full-stack-engineer"]), true);
  assert.equal(canStartPipeline({ member: "consumer", job: ["ai-product-manager"] }, ["ai-solution-architect"]), false);
  assert.equal(canStartPipeline({ member: null, job: ["ai-solution-architect"] }, []), false, "not a member");
});

const base = (): DeliveryRun => ({
  id: "r1", workspace_id: "w", pipeline: PIPE.name, pipeline_version: PIPE.version, mode: "brownfield", repo: "acme/billing", ref: "main", request: "add export",
  status: "queued", stage: "requirements", stages: seedStages(PIPE), stack_profile: null, pr: null, executor: "ide", executor_ref: null,
  created_by: "u1", api_key_id: null, created_at: "2026-10-22T09:00:00Z", updated_at: "2026-10-22T09:00:00Z", error: null,
});

test("stage reducer: queued → running → awaiting_approval → running → succeeded; stages merged by id, order kept", () => {
  const r0 = base();
  assert.deepEqual(r0.stages.map((s) => [s.id, s.status]), [["requirements", "queued"], ["architecture", "queued"], ["build", "queued"]]);
  const r1 = applyStage(r0, { id: "requirements", status: "running", started_at: "2026-10-22T09:01:00Z" });
  assert.equal(r1.status, "running");
  assert.equal(r1.stages[0].role, "ai-product-manager", "the seeded role is kept when the post omits it");
  const r2 = applyStage(r1, { id: "requirements", status: "succeeded", gate: { kind: "output", verdict: "pass" }, evidence: [{ path: "prd.md", sha256: "a".repeat(64), bytes: 12 }], finished_at: "2026-10-22T09:05:00Z" });
  assert.equal(r2.status, "running", "a passed middle stage keeps the run running");
  assert.equal(r2.stages[0].evidence?.length, 1);
  const r3 = applyStage(r2, { id: "architecture", status: "awaiting_approval", gate: { kind: "approval", verdict: "pending" } });
  assert.equal(r3.status, "awaiting_approval");
  assert.equal(awaitingStage(r3)?.id, "architecture");
  const post = approvalPost(r3.stages[1], "ann@example.test", "plan reviewed", "2026-10-22T09:10:00Z");
  const r4 = applyStage(r3, post);
  assert.equal(r4.status, "running");
  assert.deepEqual(r4.stages[1].gate, { kind: "approval", verdict: "pass", detail: "approved by ann@example.test — plan reviewed" });
  assert.equal(awaitingStage(r4), null);
  const r5 = applyStage(r4, { id: "build", status: "succeeded", gate: { kind: "exit", verdict: "pass" } });
  assert.equal(r5.status, "succeeded", "last stage ok → succeeded");
  assert.equal(r5.stage, "build");
  assert.deepEqual(r5.stages.map((s) => s.id), ["requirements", "architecture", "build"], "order kept");
  assert.equal(applyStage(r5, { id: "build", status: "failed" }), r5, "a succeeded run is immutable");
  assert.equal(r0.status, "queued", "pure: the input run is untouched");
});

test("stage reducer: a failed gate blocks; a stage error fails; an out-of-order last stage does not succeed the run; unknown stages append", () => {
  const blocked = applyStage(base(), { id: "requirements", status: "succeeded", gate: { kind: "output", verdict: "fail", detail: "no Acceptance criteria section" } });
  assert.equal(blocked.status, "blocked");
  assert.equal(blocked.error, "no Acceptance criteria section");
  const failed = applyStage(base(), { id: "requirements", status: "failed", error: "skill crashed" });
  assert.deepEqual([failed.status, failed.error], ["failed", "skill crashed"]);
  const early = applyStage(base(), { id: "build", status: "succeeded", gate: { kind: "exit", verdict: "pass" } });
  assert.equal(early.status, "running", "earlier stages are still queued");
  const extra = applyStage(base(), { id: "hotfix", status: "running", role: "ai-ops-sre" });
  assert.equal(extra.stages.length, 4);
  assert.deepEqual(extra.stages[3], { id: "hotfix", adlc_stage: "hotfix", role: "ai-ops-sre", status: "running", evidence: [] });
});

test("approval authority: an admin, or a member assigned to the stage's role", () => {
  const stage = { role: "ai-solution-architect" };
  assert.equal(canApproveStage({ member: "admin", job: [] }, stage), true);
  assert.equal(canApproveStage({ member: "reviewer", job: [] }, stage), false, "workspace reviewers do not own delivery stages");
  assert.equal(canApproveStage({ member: "consumer", job: ["ai-solution-architect"] }, stage), true);
  assert.equal(canApproveStage({ member: "author", job: ["ai-product-manager"] }, stage), false);
  assert.equal(canApproveStage({ member: "author", job: ["x"] }, { role: "" }), false, "a stage without a role is not approvable by role");
  assert.equal(canApproveStage({ member: null, job: ["ai-solution-architect"] }, stage), false);
});

test("executor: the IDE command is exact and shell-safe; GitHub dispatch posts workflow_dispatch or records why not", async () => {
  const run = { ...base(), id: "0d7b0c8e-1111-4222-8333-444444444444", request: "add 'invoice' export" };
  assert.equal(deliverCommand(run, "https://studio.example/"), `python3 scripts/deliver.py --pipeline feature-delivery --repo 'acme/billing' --ref 'main' --request 'add '\\''invoice'\\'' export' --run 0d7b0c8e-1111-4222-8333-444444444444 --portal 'https://studio.example'`);
  assert.deepEqual(workflowInputs(run, "https://studio.example/api/delivery-runs/x/stage"), { run_id: run.id, pipeline: "feature-delivery", mode: "brownfield", repo: "acme/billing", ref: "main", request: "add 'invoice' export", callback: "https://studio.example/api/delivery-runs/x/stage" });

  const none = await dispatchGithubActions(run, "https://cb", { token: "" });
  assert.deepEqual(none, { ok: false, executor_ref: "", notice: "no executor configured — run `scripts/deliver.py` from an IDE and post evidence" });
  const seen: { url: string; init: RequestInit }[] = [];
  const fakeFetch = (async (url: string | URL | Request, init?: RequestInit) => { seen.push({ url: String(url), init: init ?? {} }); return new Response(null, { status: 204 }); }) as typeof fetch;
  const ok = await dispatchGithubActions(run, "https://cb", { token: "t", repo: "acme/giri-skills", ref: "main", fetch: fakeFetch });
  assert.deepEqual(ok, { ok: true, executor_ref: "https://github.com/acme/giri-skills/actions/workflows/delivery.yml" });
  assert.equal(seen[0].url, "https://api.github.com/repos/acme/giri-skills/actions/workflows/delivery.yml/dispatches");
  assert.equal((seen[0].init.headers as Record<string, string>).authorization, "Bearer t");
  assert.deepEqual(JSON.parse(String(seen[0].init.body)), { ref: "main", inputs: workflowInputs(run, "https://cb") });
  const refused = await dispatchGithubActions(run, "https://cb", { token: "t", repo: "acme/giri-skills", fetch: (async () => new Response("Not Found", { status: 404 })) as typeof fetch });
  assert.equal(refused.ok, false);
  assert.match(refused.notice!, /HTTP 404.*Not Found/);
  assert.match((await dispatchGithubActions(run, "https://cb", { token: "t", repo: "not-a-repo" })).notice!, /DELIVERY_GITHUB_REPO must be owner\/name/);
  const ide = await dispatch({ ...run, executor: "ide" }, { callbackUrl: "https://cb", portalUrl: "https://studio.example" });
  assert.equal(ide.ok, true);
  assert.match(ide.notice!, /^run locally: python3 scripts\/deliver\.py/);
});
