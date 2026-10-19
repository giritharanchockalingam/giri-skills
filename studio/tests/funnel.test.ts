import { test } from "node:test";
import assert from "node:assert/strict";
import { gateOf } from "../lib/factory/funnel.ts";

const base = { status: "draft", publishable: false, eval_gate_met: false, eval_current: false, latest_eval_run_id: null, eval_case_count: 3, approval_valid: false, require_approval: true };
test("funnel: each version lands in exactly the stage its gates say", () => {
  assert.equal(gateOf(null, true), "published");
  assert.equal(gateOf(null, false), "draft");
  assert.equal(gateOf({ ...base, eval_case_count: 0 }, false), "draft");
  assert.equal(gateOf(base, false), "needs_eval");
  assert.equal(gateOf({ ...base, latest_eval_run_id: "r", eval_current: false }, false), "needs_eval", "cases changed since the last evaluation");
  assert.equal(gateOf({ ...base, latest_eval_run_id: "r", eval_current: true }, false), "below_bar");
  assert.equal(gateOf({ ...base, latest_eval_run_id: "r", eval_current: true, eval_gate_met: true }, true), "needs_approval");
  assert.equal(gateOf({ ...base, eval_gate_met: true, require_approval: false }, false), "ready");
  assert.equal(gateOf({ ...base, eval_gate_met: true, approval_valid: true, publishable: true }, false), "ready");
});
