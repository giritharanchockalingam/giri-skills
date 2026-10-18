/* GET /api/runtime/health — admin-only, server-side check of the Python runtime and whether ANTHROPIC_API_KEY is present there. */
import { apiContext, apiError, json } from "@/lib/factory/http";
import { can } from "@/lib/factory/roles";
import { runtimeHealth } from "@/lib/factory/runtime";

export const dynamic = "force-dynamic";

export async function GET() {
  const ctx = await apiContext();
  if (!ctx) return apiError(401, "unauthenticated", "Sign in.");
  if (!can(ctx.role, "admin.connections")) return apiError(403, "forbidden", "Admins only.");
  return json(await runtimeHealth());
}
