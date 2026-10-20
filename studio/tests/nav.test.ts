import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { SECTIONS, sectionOf } from "../lib/nav.ts";

const routes = (dir: string, base = ""): string[] => readdirSync(dir).flatMap((n) => {
  const p = join(dir, n);
  if (!statSync(p).isDirectory() || n.startsWith("_") || n === "api" || n.startsWith("(")) return [];
  const r = `${base}/${n.replace(/^\[.*\]$/, "x")}`;
  return [r, ...routes(p, r)];
});

test("five persona sections, admin last", () => {
  assert.deepEqual(SECTIONS.map((s) => s.id), ["use", "build", "govern", "platform", "admin"]);
  for (const s of SECTIONS) assert.match(s.who, /^For /, `${s.id} says who it is for`);
});

test("every page belongs to exactly one section", () => {
  const skip = /^\/(login|auth|overview|workspace)(\/|$)/;   // sign-in and redirects
  for (const r of ["/", ...routes("app")].filter((r) => !skip.test(r))) {
    const hits = SECTIONS.filter((s) => s.match(r));
    assert.equal(hits.length, 1, `${r} → ${hits.map((h) => h.id).join(",") || "none"}`);
  }
  assert.equal(sectionOf("/")?.id, "use");
});

test("raw Port data is not a navigation page", () => {
  assert.ok(!SECTIONS.flatMap((s) => s.pages).some((p) => /component|Delivery/.test(p.href + p.label)));
});
