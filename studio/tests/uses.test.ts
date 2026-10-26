import { test } from "node:test";
import assert from "node:assert/strict";
import { parseUse, skillUseLabels } from "../lib/factory/uses.ts";

const ok = { slug: "code-review-runner", version: 2, sha256: "a".repeat(64), event: "loaded", integrity: "verified", session: "3f2a9c" };

test("uses: a well-formed report from the plugin hook is accepted as-is", () => {
  assert.deepEqual(parseUse(ok), ok);
  assert.deepEqual(parseUse({ ...ok, sha256: undefined, session: undefined }), { ...ok, sha256: undefined, session: undefined });
});

test("uses: every malformed field is refused with a reason; a key-shaped session is never stored", () => {
  for (const [patch, why] of [
    [{ slug: "Bad Slug" }, /slug/], [{ version: 0 }, /version/], [{ version: 1.5 }, /version/], [{ sha256: "xyz" }, /sha256/],
    [{ event: "ran" }, /event/], [{ integrity: "ok" }, /integrity/], [{ session: "has space" }, /session/],
    [{ session: "sf_live_abcdef" }, /API key/],
  ] as const) {
    const r = parseUse({ ...ok, ...patch });
    assert.equal(typeof r, "string", JSON.stringify(patch)); assert.match(r as string, why);
  }
});

test("uses: labels say what happened in plain words", () => {
  assert.deepEqual(skillUseLabels({ event: "blocked", integrity: "modified", currency: "stale" }), { result: "Blocked", files: "Changed after approval", currency: "Older version (plugin not updated)" });
  assert.equal(skillUseLabels({ event: "loaded", integrity: "verified", currency: "current" }).files, "Approved files");
});
