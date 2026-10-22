/* Retrieval eval set for the live skill router — the BM25 search behind "Find", the front door and the MCP `route` tool
 * (lib/factory/talent.ts). Every eval prompt in the library is a labelled query: its owning skill (or, for a boundary
 * case, the neighbouring skill it belongs to) is the expected document; the router's top 5 are the retrieved documents.
 * The CSV is scored by the rag-pipeline-design skill's own script (skills/ai-platform/rag-pipeline-design/scripts/
 * eval_retrieval.py), which gates CI against evals/retrieval/router-baseline.json.
 *
 *   node --experimental-strip-types scripts/router-retrieval.mts <out.csv>
 */
import { readFileSync, writeFileSync } from "node:fs";
import { Router, type SkillInfo } from "../lib/factory/talent.ts";

type Case = { id: string; prompt?: string; routesTo?: string };
const skills = JSON.parse(readFileSync(new URL("../data/skills.json", import.meta.url), "utf8")) as (SkillInfo & { name: string; cases?: Case[] })[];
const byName = new Map(skills.map((s) => [s.name, s.id]));
const router = new Router(skills);

const cell = (v: string) => (/[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
const rows = [["query_id", "query", "expected_doc_ids", "retrieved_doc_ids", "query_type", "notes"].join(",")];
for (const s of skills) for (const c of s.cases ?? []) {
  if (!c.prompt) continue;
  const expected = c.routesTo ? byName.get(c.routesTo) : s.id;
  if (!expected) throw new Error(`${s.id} case ${c.id} routes to unknown skill ${c.routesTo}`);
  const type = c.routesTo ? "boundary" : c.id.startsWith("x-") ? "expanded" : "original";
  const retrieved = router.route(c.prompt, undefined, 5).map((h) => h.skill);
  rows.push([`${s.id}#${c.id}`, c.prompt, expected, retrieved.join("|"), type, `eval case of ${s.id}`].map(cell).join(","));
}
const out = process.argv[2];
if (!out) { console.error("usage: router-retrieval.mts <out.csv>"); process.exit(1); }
writeFileSync(out, rows.join("\n") + "\n");
console.log(`router-retrieval: ${rows.length - 1} labelled queries -> ${out}`);
