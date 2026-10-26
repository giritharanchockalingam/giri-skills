// GET /api/port/reconcile[?workspace=<uuid>][&format=text] — workspace defaults to the one with published skills; — factory vs Port (spec §6.3). Operator token.
import { NextResponse, type NextRequest } from "next/server";
import { operatorAuthorized } from "@/lib/integrations/port/serverAuth";
import { adminConfigured, createAdminSupabase } from "@/lib/supabase/server-admin";
import { reconcilePort, reconcileText } from "@/lib/integrations/port/reconcile";
import { pickPublishingWorkspace } from "@/lib/integrations/port/workspace";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

export async function GET(req: NextRequest) {
  const auth = operatorAuthorized(req.headers.get("authorization"));
  if (!auth.ok) return NextResponse.json({ error: { code: "AUTH_REQUIRED", message: auth.message } }, { status: auth.status });
  if (!adminConfigured()) return NextResponse.json({ error: { code: "NOT_CONFIGURED", message: "SUPABASE_SERVICE_ROLE_KEY is not set on the server" } }, { status: 503 });
  const admin = createAdminSupabase();
  let workspace = req.nextUrl.searchParams.get("workspace");
  if (!workspace) {
    // default to the one workspace Port mirrors: the one with published skills
    const { data } = await admin.from("sf_skills").select("workspace_id").eq("status", "published").limit(1000);
    const pick = pickPublishingWorkspace((data ?? []) as { workspace_id: string }[]);
    if (!pick.ok) return NextResponse.json({ error: { code: pick.code, message: pick.message } }, { status: pick.status });
    workspace = pick.id;
  }
  const report = await reconcilePort(admin, workspace);
  if (req.nextUrl.searchParams.get("format") === "text") return new NextResponse(reconcileText(report) + "\n", { status: 200, headers: { "content-type": "text/plain; charset=utf-8" } });
  return NextResponse.json(report);
}
