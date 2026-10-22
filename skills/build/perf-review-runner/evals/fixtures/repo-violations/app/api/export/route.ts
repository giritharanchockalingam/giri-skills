// fictional fixture — export handler parses a large JSON file on every request (perf-review-runner evals)
import { readFileSync } from "node:fs";
import path from "node:path";

export async function GET() {
  const catalog = JSON.parse(readFileSync(path.join(process.cwd(), "data", "catalog.json"), "utf8"));
  return Response.json({ items: catalog.items.length });
}
