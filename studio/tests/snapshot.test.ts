// Frozen version files (lib/factory/snapshot.ts): the server and the Python runtime must hash files identically.
import { test } from "node:test";
import assert from "node:assert/strict";
import { snapshotSha } from "../lib/factory/snapshot.ts";

test("snapshotSha matches api/py/run.py snapshot_sha (sorted by path, UTF-8, NUL-separated)", () => {
  assert.equal(snapshotSha([{ path: "b.txt", content: "é" }, { path: "SKILL.md", content: "x" }]), "5f50a239db8dbb132a45af4d145a3b70272c8762b9675ae530b2733d8209b2c9");
});

test("snapshotSha does not depend on input order and changes with any byte", () => {
  const a = [{ path: "SKILL.md", content: "x" }, { path: "scripts/a.py", content: "print(1)" }];
  assert.equal(snapshotSha(a), snapshotSha([...a].reverse()));
  assert.notEqual(snapshotSha(a), snapshotSha([{ ...a[0], content: "x " }, a[1]]));
});
