// The browser runner's Web Worker (public/run-worker.js), executed for real in Node: real Pyodide (npm, same version as
// the CDN), the real skill bundle, the real run_skill.py. Only the browser globals are provided by this harness.
import { test, before } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { loadPyodide } from "pyodide";

const posted = [];
let ctx;
const waitFor = (pred, ms = 120_000) => new Promise((resolve, reject) => {
  const t0 = Date.now();
  const tick = () => { const m = posted.find(pred); if (m) return resolve(m); if (Date.now() - t0 > ms) return reject(new Error("timeout")); setTimeout(tick, 50); };
  tick();
});

before(async () => {
  const self = {
    postMessage: (m) => posted.push(m),
    loadPyodide: () => loadPyodide(),
  };
  ctx = vm.createContext({
    self, console, setTimeout, URL, XMLHttpRequest: undefined,
    importScripts: () => {},                                   // pyodide.js is provided by the npm package instead
    fetch: async (url) => {
      assert.equal(url, "/runtime/bundle.json");
      const text = readFileSync(new URL("../public/runtime/bundle.json", import.meta.url), "utf8");
      return { ok: true, json: async () => JSON.parse(text) };
    },
  });
  vm.runInContext(readFileSync(new URL("../public/run-worker.js", import.meta.url), "utf8"), ctx);
  await ctx.self.onmessage({ data: { type: "init", pyodideBase: "" } });
  await waitFor((m) => m.type === "ready" || m.type === "error");
  assert.equal(posted.find((m) => m.type === "error"), undefined, JSON.stringify(posted.find((m) => m.type === "error")));
});

const run = async (id, skill, inputs) => {
  await ctx.self.onmessage({ data: { type: "run", id, skill, inputs, assumptions: {}, providerKey: "", model: "" } });
  return waitFor((m) => m.id === id && (m.type === "result" || m.type === "error"));
};

test("folder input (brownfield): an existing migrations folder is written and linted", async () => {
  const r = await run("f1", "build/supabase-schema-rls", { migrations: { kind: "files", files: [
    { path: "0001_notes.sql", content: "-- fictional example\ncreate table public.notes (id uuid primary key);\n" },
    { path: "0002_tags.sql", content: "-- fictional example\n-- rollback:\n--   drop table if exists public.tags;\ncreate table public.tags (id uuid primary key);\nalter table public.tags enable row level security;\ncreate policy t on public.tags for select to authenticated using (true);\n" },
    { path: "../escape.sql", content: "create table public.escape (id int);" },     // unsafe path: ignored, never written
  ] } });
  assert.equal(r.type, "result", r.message);
  const lint = r.files["rls-lint.txt"];
  assert.match(lint, /0001_notes\.sql:\d+: ERROR RLS001 table public\.notes created without/);
  assert.doesNotMatch(lint, /public\.tags|escape/);
  assert.equal(r.exitCode, 1);                                   // the gate found a real problem
});

test("text inputs still work (greenfield path unchanged)", async () => {
  const sql = "-- fictional example\n-- rollback:\n--   drop table if exists public.a;\ncreate table public.a (id uuid primary key);\nalter table public.a enable row level security;\ncreate policy p on public.a for select to authenticated using (true);\n";
  const r = await run("t1", "build/supabase-schema-rls", { migrations: { kind: "text", ext: "sql", content: sql } });
  assert.equal(r.type, "result", r.message);
  assert.match(r.files["rls-lint.txt"], /0 errors/);
});
