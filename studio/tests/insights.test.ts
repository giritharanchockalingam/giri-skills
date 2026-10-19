import { test } from "node:test";
import assert from "node:assert/strict";
import { computeInsights, weekStart, type Activity } from "../lib/insights/compute.ts";

const NOW = Date.parse("2026-10-19T12:00:00Z");
const a = (skill: string, channel: Activity["channel"], ok: boolean, daysAgo: number, user = "u1", cost: number | null = null): Activity =>
  ({ skill, channel, ok, at: new Date(NOW - daysAgo * 86_400_000).toISOString(), user, cost });

test("ROI counts only successful real work, and only where the workspace set a baseline", () => {
  const acts = [
    a("build/rls", "browser", true, 1), a("build/rls", "api", true, 2, "u2"), a("build/rls", "playbook", true, 3),
    a("build/rls", "examples", true, 1),          // demo on sample inputs: not work
    a("build/rls", "eval", true, 1),              // evaluation: not work
    a("build/rls", "api", false, 1),              // failed: not work
    a("ai/x", "portal", true, 1, "u3", 0.42),     // no baseline: no hours
    a("build/rls", "browser", true, 40),          // outside the 30-day period
  ];
  const ins = computeInsights(acts, [{ skill: "build/rls", manual_minutes: 45, hourly_rate_usd: 120, owner: "Lead", source: "timed" }], [], 30, NOW);
  const rls = ins.skills.find((s) => s.skill === "build/rls")!;
  assert.equal(rls.runs, 6); assert.equal(rls.counted, 3);
  assert.equal(rls.hours, 2.3); assert.equal(rls.value, 270);   // 3 × 45 min = 2.25 h: shown 2.3 h; value from exact hours ($270, not $276)
  const x = ins.skills.find((s) => s.skill === "ai/x")!;
  assert.equal(x.hours, null); assert.equal(x.value, null);
  assert.deepEqual(ins.roi, { hours: 2.3, value: 270, counted: 4, skillsWithBaseline: 1, skillsWithout: 1 });
  assert.equal(ins.total, 7); assert.equal(ins.people, 3); assert.deepEqual(ins.spend, { usd: 0.42, runsWithCost: 1 });
  assert.equal(ins.channels.find((c) => c.channel === "examples")!.runs, 1);
});

test("no baseline at all → no ROI number, never a guess; empty period is not a 0% success rate", () => {
  const ins = computeInsights([a("ai/x", "api", true, 1)], [], [], 7, NOW);
  assert.deepEqual(ins.roi, { hours: 0, value: null, counted: 1, skillsWithBaseline: 0, skillsWithout: 1 });
  assert.equal(computeInsights([], [], [], 7, NOW).successRate, null);
});

test("weeks start on Monday (UTC) and cover the period", () => {
  assert.equal(new Date(weekStart(Date.parse("2026-10-19T12:00:00Z"))).toISOString(), "2026-10-19T00:00:00.000Z");   // a Monday
  assert.equal(new Date(weekStart(Date.parse("2026-10-25T23:00:00Z"))).toISOString(), "2026-10-19T00:00:00.000Z");   // Sunday
  const ins = computeInsights([a("s/a", "api", true, 0), a("s/a", "api", true, 8)], [], [], 14, NOW);
  assert.equal(ins.weeks.reduce((n, w) => n + w.runs, 0), 2);
});

test("scorecards: repos passing every check, verdicts per check", () => {
  const ins = computeInsights([], [], [
    { entity_id: "r1", check_id: "rls", verdict: "pass" }, { entity_id: "r1", check_id: "nextjs", verdict: "skipped" },
    { entity_id: "r2", check_id: "rls", verdict: "fail" }, { entity_id: "r2", check_id: "nextjs", verdict: "error" }], 30, NOW);
  assert.equal(ins.scorecards.repos, 2); assert.equal(ins.scorecards.passingAll, 1);
  assert.deepEqual(ins.scorecards.byCheck, [{ check: "nextjs", pass: 0, warn: 0, fail: 0, error: 1 }, { check: "rls", pass: 1, warn: 0, fail: 1, error: 0 }]);
});
