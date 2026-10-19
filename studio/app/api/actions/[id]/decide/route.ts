/* POST /api/actions/{id}/decide — {approve: boolean, note?}. Reviewers and admins only, never on their own request
 * (enforced by sf_action_decide). An approval runs the action straight away, as the approver. */
import { z } from "zod";
import { apiContext, apiError, json, readJson } from "@/lib/factory/http";
import { runApproved } from "@/lib/actions/execute";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

const Body = z.object({ approve: z.boolean(), note: z.string().max(1000).optional() });

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in and select a workspace.");
  const { id } = await params;
  if (!z.string().uuid().safeParse(id).success) return apiError(404, "not_found", "Action not found.");
  const parsed = Body.safeParse(await readJson(req));
  if (!parsed.success) return apiError(400, "bad_request", "Body: {\"approve\": true|false, \"note\": \"…\"}.");
  const { data, error } = await ctx.supabase.rpc("sf_action_decide", { p_id: id, p_approve: parsed.data.approve, p_note: parsed.data.note ?? "" });
  if (error) return apiError(error.message.includes("only reviewers") || error.message.includes("own request") ? 403 : 409, "rejected", error.message);
  if (data !== "approved") return json({ ok: true, status: data, message: "Rejected." });
  return json(await runApproved(ctx, id));
}
