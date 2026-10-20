import { test } from "node:test";
import assert from "node:assert/strict";
import { accessPreview, parseHolder, roleCovers, type Holder, type JobRole, type PublishedSkill } from "../lib/access.ts";

const U = (id: string, access: Holder["access"]): Holder => ({ kind: "user", id, label: id, access });
const K = (id: string): Holder => ({ kind: "key", id, label: id, access: "key" });
const finance: JobRole = { id: "r1", slug: "finance", name: "Finance analyst", skills: ["ai-platform/llm-cost-model", "invoice-check"], playbooks: [] };
const skills: PublishedSkill[] = [
  { slug: "llm-cost-model", title: "LLM cost model", repoSkill: "ai-platform/llm-cost-model" },
  { slug: "invoice-check", title: "Invoice check", repoSkill: null },
  { slug: "red-team", title: "Red team", repoSkill: "ai-platform/red-team" },
];

test("a role covers a skill by library id or by workspace slug (same as the database)", () => {
  assert.ok(roleCovers(finance, skills[0]));
  assert.ok(roleCovers(finance, skills[1]));
  assert.ok(!roleCovers(finance, skills[2]));
});

test("preview: builders are never restricted; consumers and keys get their roles' skills", () => {
  const p = accessPreview({
    holders: [U("a", "admin"), U("au", "author"), U("c1", "consumer"), U("c2", "consumer"), K("k1")],
    roles: [finance], skills,
    assignments: [{ id: "x", talent_id: "r1", user_id: "c1", api_key_id: null }, { id: "y", talent_id: "r1", user_id: null, api_key_id: "k1" }],
  });
  assert.deepEqual(p.restricted.map((r) => r.holder.id), ["c1", "c2", "k1"]);
  assert.deepEqual(p.restricted[0].skills.map((s) => s.slug), ["llm-cost-model", "invoice-check"]);
  assert.deepEqual(p.withoutRole.map((h) => h.id), ["c2"]);
  assert.deepEqual(p.uncovered.map((s) => s.slug), ["red-team"]);
  assert.equal(p.restricted[2].skills.length, 2, "a key runs through its role");
});

test("an assignment to an unpublished or deleted role grants nothing", () => {
  const p = accessPreview({ holders: [U("c1", "consumer")], roles: [], skills, assignments: [{ id: "x", talent_id: "gone", user_id: "c1", api_key_id: null }] });
  assert.equal(p.withoutRole.length, 1);
});

test("holder field parsing", () => {
  assert.deepEqual(parseHolder("user:00000000-0000-0000-0000-000000000004"), { kind: "user", id: "00000000-0000-0000-0000-000000000004" });
  assert.equal(parseHolder("admin:00000000-0000-0000-0000-000000000004"), null);
  assert.equal(parseHolder("user:'; drop"), null);
});

test("what a person may run, and which roles to ask for", async () => {
  const { allowedKeysFor, rolesCovering } = await import("../lib/access.ts");
  const other: JobRole = { id: "r2", slug: "sec", name: "Security", skills: ["ai-platform/red-team"], playbooks: [] };
  const keys = allowedKeysFor("c1", [finance, other], [{ id: "a", talent_id: "r1", user_id: "c1", api_key_id: null }, { id: "b", talent_id: "r2", user_id: "c2", api_key_id: null }]);
  assert.ok(keys.has("invoice-check") && !keys.has("ai-platform/red-team"));
  assert.deepEqual(rolesCovering([finance, other], ["ai-platform/red-team", "red-team"]).map((r) => r.slug), ["sec"]);
});
