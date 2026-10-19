import { test } from "node:test";
import assert from "node:assert/strict";
import { computeDelivery, frequencyBand, leadTimeBand, percentile, fmtHours, type PrFact } from "../lib/insights/delivery.ts";

const NOW = Date.parse("2026-10-19T12:00:00Z");
const H = 3_600_000;
const pr = (n: number, openedH: number, mergedH: number | null, title = `change ${n}`, head = `feat/${n}`, extra: Partial<PrFact> = {}): PrFact => ({
  number: n, title, head_ref: head, created_at: new Date(NOW - openedH * H).toISOString(),
  merged_at: mergedH == null ? null : new Date(NOW - mergedH * H).toISOString(), closed_at: mergedH == null ? null : new Date(NOW - mergedH * H).toISOString(), ...extra });

test("delivery: bands follow DORA 2024 deployment-frequency and lead-time clusters", () => {
  assert.equal(frequencyBand(10), "elite");
  assert.equal(frequencyBand(7), "elite");
  assert.equal(frequencyBand(2), "high");
  assert.equal(frequencyBand(0.5), "medium");
  assert.equal(frequencyBand(0.1), "low");
  assert.equal(leadTimeBand(3), "elite");
  assert.equal(leadTimeBand(30), "high");
  assert.equal(leadTimeBand(24 * 10), "medium");
  assert.equal(leadTimeBand(24 * 60), "low");
});

test("delivery: merges in the window, lead time median/p75, change-failure proxy, open PRs", () => {
  const prs = [
    pr(1, 10, 8), pr(2, 30, 20), pr(3, 50, 2, "Revert \"change 2\""), pr(4, 100, 40, "fix login", "hotfix/login"),
    pr(5, 24 * 40, 24 * 35),                 // merged before a 30-day window
    pr(6, 72, null), pr(7, 5, null, "wip", "x", { draft: true }), // open (one draft)
  ];
  const d = computeDelivery(prs, null, 30, NOW);
  assert.equal(d.merges, 4);
  assert.equal(d.deploys.source, "merges");
  assert.equal(d.deploys.count, 4);
  assert.equal(d.deploys.per_week, Math.round((4 / (30 / 7)) * 10) / 10);
  // lead times: 2, 10, 48, 60 hours → median 29, p75 51
  assert.equal(d.lead_time.median_hours, 29);
  assert.equal(d.lead_time.p75_hours, 51);
  assert.equal(d.lead_time.band, "high");
  assert.equal(d.change_failure.failures, 2);
  assert.equal(d.change_failure.rate, 50);
  assert.deepEqual(d.open_prs, { count: 1, oldest_days: 3 });
});

test("delivery: production deployments are used when GitHub has them; nothing invented when empty", () => {
  const deploys = [{ created_at: new Date(NOW - 2 * H).toISOString(), environment: "Production" }, { created_at: new Date(NOW - 3 * H).toISOString(), environment: "Preview" },
    { created_at: new Date(NOW - 5 * H).toISOString(), environment: "production" }];
  const d = computeDelivery([pr(1, 10, 8)], deploys, 7, NOW);
  assert.deepEqual([d.deploys.source, d.deploys.count], ["deployments", 2]);
  const linked = computeDelivery([pr(1, 10, 8)], [], 30, NOW, true);
  assert.deepEqual([linked.deploys.source, linked.deploys.count, linked.deploys.band], ["deployments", 0, null], "Vercel says zero: zero, not merges");
  const empty = computeDelivery([], [], 30, NOW);
  assert.deepEqual([empty.deploys.count, empty.deploys.band, empty.lead_time.median_hours, empty.lead_time.band, empty.change_failure.rate], [0, null, null, null, null]);
});

test("delivery: helpers", () => {
  assert.equal(percentile([], 0.5), null);
  assert.equal(percentile([4], 0.75), 4);
  assert.equal(fmtHours(0.5), "30 min");
  assert.equal(fmtHours(30), "30 h");
  assert.equal(fmtHours(72), "3 days");
});
