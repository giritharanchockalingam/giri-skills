import { test } from "node:test";
import assert from "node:assert/strict";
import { humanName, shortOutcome } from "../lib/names.ts";

test("humanName: acronyms and runner suffix", () => {
  assert.equal(humanName("ai-bom-license-check"), "AI BOM license check");
  assert.equal(humanName("langgraph-hitl-runner"), "LangGraph HITL");
  assert.equal(humanName("ci-cd-vercel-github"), "CI CD Vercel GitHub");
  assert.equal(humanName("multi-tenant-saas-patterns"), "Multi tenant SaaS patterns");
  assert.equal(humanName("ai-finops-chargeback"), "AI FinOps chargeback");
});

test("shortOutcome: first clause, no verb, bounded", () => {
  assert.equal(shortOutcome("Produces a forward-only migration SQL with a rollback block, RLS policies and seed data."), "Forward-only migration SQL");
  assert.equal(shortOutcome("Produces classification."), "Classification");
  const long = shortOutcome("Produces one two three four five six seven eight nine ten eleven twelve thirteen fourteen");
  assert.ok(long.split(/\s+/).length <= 12 && long.endsWith("…"));
});
