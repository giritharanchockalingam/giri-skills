import { test } from "node:test";
import assert from "node:assert/strict";
import { collapseNotes } from "../lib/insights/notes.ts";

test("one line per lead-in, not one per repository", () => {
  const out = collapseNotes(["Deploys: successful Vercel production deployments of a.", "Deploys: successful Vercel production deployments of b, c.", "Deploys: successful Vercel production deployments of d.", "Deploys: successful Vercel production deployments of e.", "Lead time unavailable."]);
  assert.deepEqual(out, ["Deploys: successful Vercel production deployments of 5 services (a, b, c, and 2 more).", "Lead time unavailable."]);
});

test("a single service reads naturally", () => {
  assert.deepEqual(collapseNotes(["Deploys: successful Vercel production deployments of a."]), ["Deploys: successful Vercel production deployments of a."]);
});
