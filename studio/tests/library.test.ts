import { test } from "node:test";
import assert from "node:assert/strict";
import { libraryRows, librarySummary, matchesLibraryFilter, evidenceOf } from "../lib/library.ts";

const row = (id: string, verdict: "OK" | "BODY" | null, published: number | null) => ({ id, title: id, outcome: "x", stage: "Build", domain: "build", verdict, published });

test("approved first, then proven, then title", () => {
  const r = libraryRows([row("c", "OK", null), row("b", "BODY", 2), row("a", "BODY", null), row("d", null, null)]);
  assert.deepEqual(r.map((x) => x.id), ["b", "c", "a", "d"]);
});

test("evidence is said in words, never as a code or score", () => {
  assert.equal(evidenceOf("OK").label, "Proven");
  assert.equal(evidenceOf("BOTH").label, "Being improved");
  assert.equal(evidenceOf(null).label, "Not evaluated");
  for (const v of ["OK", "DESC", "BODY", "BOTH", null] as const) assert.doesNotMatch(evidenceOf(v).note, /lift|trigger|\d\.\d/i);
});

test("summary and filters", () => {
  const r = libraryRows([row("a", "OK", 1), row("b", "OK", null), row("c", "BODY", null)]);
  assert.deepEqual(librarySummary(r), { total: 3, approved: 1, proven: 2 });
  assert.equal(r.filter((x) => matchesLibraryFilter("approved", x)).length, 1);
  assert.equal(r.filter((x) => matchesLibraryFilter("proven", x)).length, 2);
});

test("published versions by library skill: highest published, repo-sourced only", async () => {
  const { publishedByLibrarySkill } = await import("../lib/library.ts");
  const m = publishedByLibrarySkill([
    { status: "published", version: 1, source: { kind: "repo", repo_skill: "a/x" } },
    { status: "published", version: 2, source: { kind: "repo", repo_skill: "a/x" } },
    { status: "draft", version: 3, source: { kind: "repo", repo_skill: "a/x" } },
    { status: "published", version: 1, source: { kind: "authored" } },
  ]);
  assert.deepEqual([...m], [["a/x", 2]]);
});
