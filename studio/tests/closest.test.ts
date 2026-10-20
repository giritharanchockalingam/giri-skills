import { test } from "node:test";
import assert from "node:assert/strict";
import { closestToPublish } from "../lib/factory/funnel.ts";

const base = { passRate: null, minPassRate: 0.8, cases: 0, version: 1 };
test("closest to publishable: stage order, then smallest gap, then most cases; published excluded", () => {
  const rows = closestToPublish([
    { ...base, slug: "d", name: "D", gate: "draft" },
    { ...base, slug: "far", name: "Far", gate: "below_bar", passRate: 0.4 },
    { ...base, slug: "near", name: "Near", gate: "below_bar", passRate: 0.75 },
    { ...base, slug: "p", name: "P", gate: "published" },
    { ...base, slug: "e3", name: "E3", gate: "needs_eval", cases: 3 },
    { ...base, slug: "e9", name: "E9", gate: "needs_eval", cases: 9 },
    { ...base, slug: "a", name: "A", gate: "needs_approval" },
    { ...base, slug: "r", name: "R", gate: "ready" },
  ], 10);
  assert.deepEqual(rows.map((r) => r.slug), ["r", "a", "near", "far", "e9", "e3", "d"]);
  assert.equal(rows[2].missing, "5% more pass rate (75% now, 80% required)");
  assert.equal(rows[4].missing, "an evaluation run on its 9 cases");
  assert.equal(rows[0].tab, "release");
  assert.equal(closestToPublish([{ ...base, slug: "x", name: "X" }]).length, 0, "no stage known: not ranked");
});
