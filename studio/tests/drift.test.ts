import { test } from "node:test";
import assert from "node:assert/strict";
import { driftOf, skillDrift } from "../lib/factory/drift.ts";

const repo = (sha?: string) => ({ kind: "repo" as const, repo_skill: "ai-platform/x", content_sha: sha });
test("drift: a published version whose library files changed is blocked; a draft is only out of date", () => {
  assert.equal(driftOf(repo("a"), "published", "a"), "current");
  assert.equal(driftOf(repo("a"), "published", "b"), "blocked");
  assert.equal(driftOf(repo("a"), "approved", "b"), "blocked");
  assert.equal(driftOf(repo("a"), "draft", "b"), "library_updated");
  assert.equal(driftOf(repo("a"), "published", null), "blocked", "removed from the library");
  assert.equal(driftOf({ kind: "authored" }, "published", "b"), "n/a");
  assert.equal(driftOf(repo(undefined), "published", "b"), "n/a", "pre-pinning versions are not judged");
});
test("skill drift: a blocked live version wins; a newer current draft does not hide it", () => {
  const pin = () => "b";
  assert.equal(skillDrift([{ source: repo("a"), status: "published", version: 1 }, { source: repo("b"), status: "draft", version: 2 }], pin), "blocked");
  assert.equal(skillDrift([{ source: repo("b"), status: "published", version: 2 }, { source: repo("a"), status: "superseded", version: 1 }], pin), "current");
  assert.equal(skillDrift([{ source: repo("a"), status: "draft", version: 1 }], pin), "library_updated");
});

import { contractKey } from "../lib/factory/drift.ts";
test("contract drift: a new library input flags the skill; instruction edits do not", () => {
  const lib = contractKey({ inputs: [{ name: "workload", type: "csv", required: true }, { name: "actuals", type: "csv" }], run: [{ step: "s", cmd: "x" }], outputs: [] });
  const old = contractKey({ inputs: [{ name: "workload", type: "csv", required: true }], run: [{ step: "s", cmd: "x" }], outputs: [] });
  const v = { source: repo("b"), status: "published", version: 1 };
  assert.equal(skillDrift([{ ...v, contract: old }], () => "b", lib), "library_updated");
  assert.equal(skillDrift([{ ...v, contract: lib }], () => "b", lib), "current");
  assert.equal(contractKey({ inputs: [], run: [], outputs: [], ...{ instructions_md: "edited" } } as never), contractKey({ inputs: [], run: [], outputs: [] }));
});
test("skill drift: a current draft whose copy of the library's test cases is older is offered the update", () => {
  const pin = () => "b";
  assert.equal(skillDrift([{ source: repo("b"), status: "draft", version: 1 }], pin, null, true), "library_updated");
  assert.equal(skillDrift([{ source: repo("b"), status: "draft", version: 1 }], pin, null, false), "current");
  assert.equal(skillDrift([{ source: repo("b"), status: "published", version: 1 }], pin, null, true), "current", "only a draft is judged on its cases");
});
test("skill drift: a library draft imported before pinning is offered the update (which pins it)", () => {
  assert.equal(skillDrift([{ source: repo(undefined), status: "draft", version: 1 }], () => "b"), "library_updated");
  assert.equal(skillDrift([{ source: repo(undefined), status: "published", version: 1 }], () => "b"), "n/a", "a live pre-pinning version is not judged");
});
test("skill drift: a live version with frozen files is out of date, not blocked, when the library moves on", () => {
  const pin = () => "b";
  const live = { id: "v1", source: repo("a"), status: "published", version: 1 };
  assert.equal(skillDrift([live], pin), "blocked", "without frozen files it cannot run");
  assert.equal(skillDrift([live], pin, null, false, new Set(["v1"])), "library_updated");
});
