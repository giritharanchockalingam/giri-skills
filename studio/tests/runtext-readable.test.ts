import { test } from "node:test";
import assert from "node:assert/strict";
import { readableError } from "../lib/runText.ts";

test("legacy generic run errors read plainly, without the contradicting zero; specific errors pass through", () => {
  assert.equal(readableError("1 step(s) not ok, 0 check(s) failed"), "1 step failed (open the run for which)");
  assert.equal(readableError("2 step(s) not ok, 3 check(s) failed"), "2 steps failed and 3 output checks failed (open the run for which)");
  assert.equal(readableError("step 'render' failed: exit 1"), "step 'render' failed: exit 1");
  assert.equal(readableError(null), "");
});
