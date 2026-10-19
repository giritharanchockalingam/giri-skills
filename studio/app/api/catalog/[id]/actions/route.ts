/* GET  /api/catalog/{id}/actions — the skills that can run on this repository (form fields) and its folders.
 * POST /api/catalog/{id}/actions — request an action: {skill, inputs: {name: {folder}|{text}}, reason}. Runs at once
 * unless workspace policy requires a reviewer's approval (decided in the database). */
import { z } from "zod";
import { apiContext, apiError, json, readJson } from "@/lib/factory/http";
import { actionCatalog, repoFolders, requestAction } from "@/lib/actions/execute";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

const Id = z.string().uuid();
const Body = z.object({
  skill: z.string().regex(/^[a-z0-9-]+$/).max(80),
  inputs: z.record(z.string().max(80), z.union([z.object({ folder: z.string().max(400) }).strict(), z.object({ text: z.string().max(200_000) }).strict()])),
  reason: z.string().max(1000).optional(),
});

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  const { id } = await params;
  if (!Id.safeParse(id).success) return apiError(404, "not_found", "Repository not found.");
  const cat = await actionCatalog(ctx, id);
  if (!cat) return apiError(404, "not_found", "Repository not in this workspace's catalog.");
  let folders: string[] = [], foldersError: string | null = null;
  try { folders = await repoFolders(ctx, id); } catch (e) { foldersError = (e as Error).message; }
  return json({ ...cat, folders, folders_error: foldersError });
}

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  const { id } = await params;
  if (!Id.safeParse(id).success) return apiError(404, "not_found", "Repository not found.");
  const parsed = Body.safeParse(await readJson(req));
  if (!parsed.success) return apiError(400, "bad_request", parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "));
  const r = await requestAction(ctx, id, parsed.data.skill, parsed.data.inputs, parsed.data.reason ?? "");
  return json(r, r.ok ? (r.status === "pending_approval" ? 202 : 200) : 422);
}
