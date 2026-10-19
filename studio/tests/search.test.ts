import { test } from "node:test";
import assert from "node:assert/strict";
import { matches } from "../lib/search.ts";

test("search: words in any order, punctuation and case ignored", () => {
  assert.ok(matches("red team", "ai-red-team", ""));
  assert.ok(matches("red-team", "AI Red Team review"));
  assert.ok(matches("rls supabase", "supabase-schema-rls"));
  assert.ok(matches("redteam", "red-team"));
  assert.ok(matches("", "anything"));
  assert.ok(!matches("red blue", "red-team"));
  assert.ok(matches("EU AI Act", "eu-ai-act-classifier"));
});

import { failureText } from "../lib/runText.ts";
test("run failure text says what failed", () => {
  assert.equal(failureText({ steps: [{ step: "lint", ok: false, error: "gate: FAIL — 77 high-severity finding(s)" }], checks: [{ pass: true }] }),
    "the skill's gate in step 'lint' said FAIL — 77 high-severity finding(s)");
  assert.equal(failureText({ steps: [{ step: "build", ok: false, error: "", exit: 2 }], checks: [{ pass: false, check: "exists", path: "/tmp/out/report.md" }] }),
    "step 'build' failed (exit 2); 1 output check(s) failed, e.g. exists on report.md");
});
