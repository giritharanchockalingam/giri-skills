import { test } from "node:test";
import assert from "node:assert/strict";
import { isKeyBearingDeliveryRequest } from "../lib/delivery/auth.ts";

test("executor callbacks with an API key bypass the session wall; everything else does not", () => {
  assert.equal(isKeyBearingDeliveryRequest("/api/delivery-runs/abc/stage", "Bearer sf_live_x"), true);
  assert.equal(isKeyBearingDeliveryRequest("/api/delivery-runs/abc", "bearer sf_live_x"), true);
  assert.equal(isKeyBearingDeliveryRequest("/api/delivery-runs/abc/stage", null), false);
  assert.equal(isKeyBearingDeliveryRequest("/api/delivery-runs/abc/stage", "Bearer "), false);
  assert.equal(isKeyBearingDeliveryRequest("/api/eval-runs/abc", "Bearer sf_live_x"), false);
  assert.equal(isKeyBearingDeliveryRequest("/deliver", "Bearer sf_live_x"), false);
});
