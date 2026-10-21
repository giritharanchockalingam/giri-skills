import { test } from "node:test";
import assert from "node:assert/strict";
import { levelOf, factsOf, atLeast } from "../lib/scorecards/levels.ts";
import { progressOf } from "../lib/scorecards/initiatives.ts";

// a Next.js + Supabase app: all four checks apply (rls, tenancy need migrations; nextjs, observability need Next.js)
const full = { stack: [{ id: "nextjs" }, { id: "supabase" }], counts: { migrations: 3, files: 120 } };
const nextOnly = { stack: [{ id: "nextjs" }], counts: { migrations: 0, files: 40 } };
const none = { stack: [{ id: "python" }], counts: { migrations: 0, files: 10 } };
const v = (o: Record<string, string>) => Object.entries(o).map(([check_id, verdict]) => ({ check_id, verdict }));

test("levels: the rules", () => {
  assert.equal(levelOf(factsOf(none), []).level, "n/a");
  assert.deepEqual(levelOf(factsOf(nextOnly), []).applicable.sort(), ["nextjs", "observability"]);

  const unscored = levelOf(factsOf(nextOnly), v({ nextjs: "pass" }));
  assert.equal(unscored.level, "none");
  assert.equal(unscored.next, "bronze");
  assert.deepEqual(unscored.blockers.map((b) => [b.check_id, b.reason]), [["observability", "not scored yet"]]);

  assert.equal(levelOf(factsOf(nextOnly), v({ nextjs: "pass", observability: "error" })).level, "none", "an errored run is not a measurement");
  const bronze = levelOf(factsOf(nextOnly), v({ nextjs: "fail", observability: "pass" }));
  assert.equal(bronze.level, "bronze");
  assert.deepEqual(bronze.blockers.map((b) => [b.check_id, b.reason]), [["nextjs", "fails"]]);
  const silver = levelOf(factsOf(nextOnly), v({ nextjs: "warn", observability: "pass" }));
  assert.equal(silver.level, "silver");
  assert.deepEqual(silver.blockers.map((b) => [b.check_id, b.reason]), [["nextjs", "has warnings"]]);
  const gold = levelOf(factsOf(full), v({ nextjs: "pass", observability: "pass", rls: "pass", tenancy: "pass" }));
  assert.equal(gold.level, "gold");
  assert.equal(gold.next, null);
  assert.deepEqual(gold.blockers, []);
  // a check that does not apply never counts, even if a stale verdict exists
  assert.equal(levelOf(factsOf(nextOnly), v({ nextjs: "pass", observability: "pass", rls: "fail" })).level, "gold");
});

test("levels: atLeast", () => {
  assert.ok(atLeast("gold", "silver") && atLeast("silver", "silver") && !atLeast("bronze", "silver"));
  assert.ok(!atLeast("none", "bronze") && !atLeast("n/a", "bronze"));
});

test("initiatives: progress is read from the scorecard, scope defaults to repos a check applies to", () => {
  const ents = [
    { id: "a", key: "acme/web", properties: full },
    { id: "b", key: "acme/site", properties: nextOnly },
    { id: "c", key: "acme/scripts", properties: none },
  ];
  const latest = new Map([
    ["a", v({ nextjs: "pass", observability: "pass", rls: "warn", tenancy: "pass" })],
    ["b", v({ nextjs: "fail", observability: "pass" })],
  ]);
  const today = new Date("2026-10-19T12:00:00Z");
  const p = progressOf({ target_level: "silver", repos: [], due_on: "2026-12-01" }, ents, latest, today);
  assert.deepEqual(p.repos.map((r) => [r.key, r.met]), [["acme/site", false], ["acme/web", true]], "unmet first; acme/scripts (no check applies) out of scope");
  assert.equal(p.pct, 50);
  assert.equal(p.daysLeft, 44);
  assert.equal(p.overdue, false);

  const named = progressOf({ target_level: "gold", repos: ["ACME/web", "acme/gone", "acme/scripts"], due_on: "2026-10-01" }, ents, latest, today);
  assert.deepEqual(named.repos.map((r) => [r.key, r.met, r.note ?? ""]), [
    ["acme/gone", false, "not in the catalog"],
    ["acme/scripts", false, "no check applies, so no level can be reached"],
    ["acme/web", false, ""],
  ]);
  assert.ok(named.overdue && named.daysLeft < 0);
});

test("initiative state: never 'on track' at 0%, 'behind' when progress trails elapsed time", async () => {
  const { initiativeState } = await import("../lib/scorecards/initiatives.ts");
  const p = (met: number, total: number, daysLeft = 40) => ({ repos: [], met, total, pct: total ? Math.round((met / total) * 100) : 0, daysLeft, overdue: daysLeft < 0 && met < total });
  const ini = { created_at: "2026-10-01T00:00:00Z", due_on: "2026-12-31" };
  const today = new Date("2026-11-15T00:00:00Z");   // about half the time used
  assert.equal(initiativeState(p(0, 35), ini, today), "not started");
  assert.equal(initiativeState(p(5, 35), ini, today), "behind");
  assert.equal(initiativeState(p(30, 35), ini, today), "on track");
  assert.equal(initiativeState(p(35, 35), ini, today), "met");
  assert.equal(initiativeState(p(5, 35, -2), ini, today), "overdue");
  assert.equal(initiativeState(p(5, 35), { ...ini, status: "closed" }, today), "closed");
});
