import { test } from "node:test";
import assert from "node:assert/strict";
import { pickPublishingWorkspace } from "../lib/integrations/port/workspace.ts";

test("reconcile default workspace: the single workspace with published skills; none → 404; several → 400 asking for one", () => {
  assert.deepEqual(pickPublishingWorkspace([{ workspace_id: "w1" }, { workspace_id: "w1" }]), { ok: true, id: "w1" });
  const none = pickPublishingWorkspace([]); assert.ok(!none.ok && none.status === 404);
  const two = pickPublishingWorkspace([{ workspace_id: "w1" }, { workspace_id: "w2" }]); assert.ok(!two.ok && two.status === 400 && /2 workspaces/.test(two.message));
});
