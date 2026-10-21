import { test } from "node:test";
import assert from "node:assert/strict";
import { readableError } from "../lib/runText.ts";

test("legacy generic run errors read plainly, without the contradicting zero; specific errors pass through", () => {
  assert.equal(readableError("1 step(s) not ok, 0 check(s) failed"), "1 step failed (open the run for which)");
  assert.equal(readableError("2 step(s) not ok, 3 check(s) failed"), "2 steps failed and 3 output checks failed (open the run for which)");
  assert.equal(readableError("step 'render' failed: exit 1"), "step 'render' failed: exit 1");
  assert.equal(readableError(null), "");
});

test("legacy failure text keeps its reason in words", async () => {
  const { readableError } = await import("../lib/runText.ts");
  assert.equal(readableError("1 step(s) not ok, 0 check(s) failed (partial: the folder is larger than the scan limit)"), "Output incomplete: the folder is larger than the scan limit.");
});

test("engine messages read plainly; the failure class never contradicts the checks", async () => {
  const { plainError, failureText } = await import("../lib/runText.ts");
  assert.equal(plainError("model 'fict-medium' has no row in the price sheet"), "the cost model has no price for the model used (fict-medium)");
  assert.equal(plainError("Traceback (most recent call last):\n  File x"), "the step's program stopped with an error");
  assert.equal(plainError("something new\nmore"), "something new");
  const t = failureText({ steps: [{ step: "cost", ok: false, error: "model 'x' has no row in the price sheet" }], checks: [{ pass: true }, { pass: true }] });
  assert.match(t, /^a step errored, although every check that ran passed — step 'cost' failed: the cost model has no price/);
  assert.match(failureText({ steps: [{ step: "a", ok: false }], checks: [] }), /^a step errored before any check ran/);
});
