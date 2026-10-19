/* POST /api/v1/skills/{slug}/run {inputs, assumptions?} — runs the PUBLISHED version only.
 * Inputs are validated against the manifest before anything executes; the output contract is validated after.
 * Synchronous within the version's deadline (≤ 55 s): returns 200 with the result, or 202 + a status URL if the
 * run was accepted but the runtime could not finish in time (status "timeout" is then visible at GET /runs/{id}).
 * Duplicate submissions: send `Idempotency-Key`; the same key returns the first run. */
import { authenticateApiKey } from "@/lib/factory/apikey";
import { json, readJson } from "@/lib/factory/http";
import { runPublishedSkill } from "@/lib/factory/apiRun";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

export async function POST(req: Request, { params }: { params: Promise<{ slug: string }> }) {
  const caller = await authenticateApiKey(req);
  if (caller instanceof Response) return caller;
  const { slug } = await params;
  const out = await runPublishedSkill(caller, slug, await readJson(req), req.headers.get("idempotency-key")?.slice(0, 120) || null, req.url);
  return json(out.body, out.http);
}
