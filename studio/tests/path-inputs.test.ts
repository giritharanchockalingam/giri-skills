// Path inputs on the hosted runtime (lib/factory/runtime.ts pathInputs): always under the run folder.
import { test } from "node:test";
import assert from "node:assert/strict";
import { pathInputs } from "../lib/factory/runtime.ts";

const manifest = { inputs: [{ name: "target", type: "path", required: true }, { name: "seed", type: "dir", required: false }, { name: "state", type: "string", required: true }] } as never;

test("a path input with nothing given defaults to the run folder", () => {
  assert.deepEqual(pathInputs(manifest, {}).target, { kind: "value", value: "{out}/target" });
});

test("an example folder given for a path input is copied into the run folder, never written in place", () => {
  assert.deepEqual(pathInputs(manifest, { target: { kind: "fixture", path: "evals/fixtures/repo" } }).target, { kind: "fixture", path: "evals/fixtures/repo", into_out: true });
});

test("a value under the run folder is kept; any other value is replaced", () => {
  assert.deepEqual(pathInputs(manifest, { target: { kind: "value", value: "{out}/repo" } }).target, { kind: "value", value: "{out}/repo" });
  assert.deepEqual(pathInputs(manifest, { target: { kind: "value", value: "/etc" } }).target, { kind: "value", value: "{out}/target" });
});

test("a case that checks the skill asks for the missing path input gets no default for it", () => {
  const out = pathInputs(manifest, {}, ["exit:2", "needs_input:target"]);
  assert.equal("target" in out, false);
});

test("non-path inputs pass through untouched", () => {
  const seed = { kind: "fixture" as const, path: "evals/fixtures/repo-existing" };
  assert.deepEqual(pathInputs(manifest, { seed, state: { kind: "value", value: "green" } }).seed, seed);
});
