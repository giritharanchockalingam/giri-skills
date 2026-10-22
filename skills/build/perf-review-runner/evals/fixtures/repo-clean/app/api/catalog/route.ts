// fictional fixture — catalog handler: the JSON file is read once at module scope, not per request (perf-review-runner evals)
import { readFileSync } from "node:fs";
import path from "node:path";

const catalog = JSON.parse(readFileSync(path.join(process.cwd(), "data", "catalog.json"), "utf8"));

export async function GET() {
  return Response.json({ items: catalog.items.length });
}
