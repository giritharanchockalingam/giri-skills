import { test } from "node:test";
import assert from "node:assert/strict";
import { fieldsFor, foldersOf, filesUnder, checkRequest, usesModel } from "../lib/actions/plan.ts";

const f = (path: string, size = 100) => ({ path, sha: path, size });
const TREE = [f("README.md"), f("supabase/migrations/0001_a.sql"), f("supabase/migrations/0002_b.sql"), f("app/page.tsx"), f("app/api/x/route.ts"), f("node_modules/react/index.js"), f(".next/cache/x")];
const manifest = {
  inputs: [
    { name: "migrations", type: "dir", required: true, from: "the migrations folder", default: null, flag: null, schema: null },
    { name: "tenant_column", type: "string", required: false, from: "", default: "auto", flag: null, schema: null },
    { name: "notes", type: "md", required: true, from: "context", default: null, flag: null, schema: null },
  ],
  run: [{ kind: "script" }, { kind: "llm" }],
} as never;

test("actions: folders exclude build/vendor dirs; '.' is the whole repository", () => {
  assert.deepEqual(foldersOf(TREE), [".", "app", "app/api", "app/api/x", "supabase", "supabase/migrations"]);
});

test("actions: files under a folder, relative strip, traversal refused", () => {
  const s = filesUnder(TREE, "supabase/migrations/");
  assert.deepEqual(s.files.map((x) => x.path), ["supabase/migrations/0001_a.sql", "supabase/migrations/0002_b.sql"]);
  assert.equal(s.strip, "supabase/migrations");
  assert.equal(filesUnder(TREE, ".").files.length, 5, "whole repo minus node_modules/.next");
  assert.equal(filesUnder(TREE, "../etc").files.length, 0);
});

test("actions: form fields from the manifest; suggested folder; model use", () => {
  const fields = fieldsFor(manifest, { migrations: "supabase/migrations" });
  assert.deepEqual(fields.map((x) => [x.name, x.kind, x.required]), [["migrations", "folder", true], ["tenant_column", "text", false], ["notes", "text", true]]);
  assert.equal((fields[0] as { suggested: string }).suggested, "supabase/migrations");
  assert.equal((fields[2] as { multiline: boolean }).multiline, true);
  assert.equal(usesModel(manifest), true);
  assert.equal(usesModel({ run: [{ kind: "script" }] } as never), false);
});

test("actions: request checks — folder must exist, required present, no unknown inputs, right kinds", () => {
  const fields = fieldsFor(manifest);
  const folders = foldersOf(TREE);
  assert.deepEqual(checkRequest(fields, { migrations: { folder: "supabase/migrations" }, notes: { text: "x" } }, folders), []);
  assert.deepEqual(checkRequest(fields, { migrations: { folder: "./" }, notes: { text: "x" } }, folders), []);
  assert.deepEqual(checkRequest(fields, { migrations: { folder: "db" }, notes: { text: " " }, extra: { text: "y" } }, folders),
    ["extra: not an input of this skill", "migrations: no folder “db” in the repository", "notes: required"]);
  assert.deepEqual(checkRequest(fields, { migrations: { text: "x" }, notes: { folder: "app" } } as never, folders), ["migrations: expects a folder", "notes: required", "notes: expects text"]);
});
