// User-facing copy follows the glossary (lib/nav.ts GLOSSARY): a regression guard for the words the audit found.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join } from "node:path";

const files = (dir: string): string[] => readdirSync(dir).flatMap((n) => { const p = join(dir, n); return statSync(p).isDirectory() ? files(p) : p.endsWith(".tsx") ? [p] : []; });
const UI = [...files("app"), ...files("components")];
const BANNED: [RegExp, string][] = [
  [/Create pool|Create \$\{kind\}/, "a team is not a pool"],
  [/tools? live\b|live tools?\b/i, "a published skill is not a 'live tool'"],
  [/chained into agents/, "skills are chained into playbooks"],
  [/No agents in this workspace/, "playbooks, not agents"],
  [/>Activity</, "the page is Runs"],
  [/vendor_sync\.py/, "operator instructions are not user copy"],
];

test("no banned synonym in user-facing copy", () => {
  const hits: string[] = [];
  for (const f of UI) { const s = readFileSync(f, "utf8"); for (const [re, why] of BANNED) if (re.test(s)) hits.push(`${f}: ${why}`); }
  assert.deepEqual(hits, []);
});

test("old addresses redirect to the glossary's names, and the old folders are gone", () => {
  const cfg = readFileSync("next.config.ts", "utf8");
  for (const [from, to] of [["/repo", "/library"], ["/agents", "/playbooks"], ["/pools", "/teams"], ["/upstream", "/reference"], ["/activity", "/runs"]]) {
    assert.ok(cfg.includes(`["${from}", "${to}"]`), `${from} → ${to}`);
    assert.ok(!existsSync(`app${from}`), `app${from} removed`);
  }
});
