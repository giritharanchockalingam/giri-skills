import { test } from "node:test";
import assert from "node:assert/strict";
import { auditActor, auditEntity, auditDetails, type AuditLookups } from "../lib/auditLabel.ts";

const U = "00000000-0000-0000-0000-000000000001", K = "11111111-1111-1111-1111-111111111111", S = "22222222-2222-2222-2222-222222222222", V = "33333333-3333-3333-3333-333333333333";
const l: AuditLookups = { me: "x", users: new Map([[U, "ana@example.com"]]), keys: new Map([[K, "port"]]), skills: new Map([[S, "LLM cost model"]]), versions: new Map([[V, "LLM cost model v2"]]) };

test("audit cells name people, keys, skills and versions; ids and hashes are short with the full value kept", () => {
  assert.equal(auditActor({ actor_kind: "user", actor_id: U, entity_type: "skill", entity_id: S, details: {} }, l).text, "ana@example.com");
  assert.equal(auditActor({ actor_kind: "api_key", actor_id: K, entity_type: "run", entity_id: null, details: {} }, l).text, "key port");
  assert.equal(auditEntity({ actor_kind: "user", actor_id: U, entity_type: "skill", entity_id: S, details: {} }, l).text, "skill LLM cost model");
  assert.equal(auditEntity({ actor_kind: "user", actor_id: U, entity_type: "version", entity_id: V, details: {} }, l).text, "LLM cost model v2");
  const run = auditEntity({ actor_kind: "user", actor_id: U, entity_type: "run", entity_id: V, details: {} }, l);
  assert.deepEqual([run.text, run.href, run.title], ["run 33333333", `/runs/${V}`, V]);
  const d = auditDetails({ actor_kind: "user", actor_id: U, entity_type: "version", entity_id: V, details: { manifest_hash: "a".repeat(64), version_id: V, note: "ok" } }, l);
  assert.deepEqual(d.map((x) => x.cell.text), ["aaaaaaaa", "LLM cost model v2", "ok"]);
  assert.equal(d[0].cell.title, "a".repeat(64));
});
