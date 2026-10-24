// GET /api/port/reconcile?workspace=<uuid>[&format=text] — factory vs Port (spec §6.3). Operator token.
import { NextResponse, type NextRequest } from "next/server";
import { operatorAuthorized } from "@/lib/integrations/port/serverAuth";
import { adminConfigured, createAdminSupabase } from "@/lib/supabase/server-admin";
import { reconcilePort, reconcileText } from "@/lib/integrations/port/reconcile";

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
    const { data } = await admin.from("sf_workspaces").select("id").order("created_at").limit(2);
    if (!data?.length) return NextResponse.json({ error: { code: "NO_WORKSPACE", message: "no workspace" } }, { status: 404 });
    if (data.length > 1) return NextResponse.json({ error: { code: "AMBIGUOUS", message: "several workspaces: pass ?workspace=<uuid>" } }, { status: 400 });
    workspace = data[0].id as string;
  }
  const report = await reconcilePort(admin, workspace);
  if (req.nextUrl.searchParams.get("format") === "text") return new NextResponse(reconcileText(report) + "\n", { status: 200, headers: { "content-type": "text/plain; charset=utf-8" } });
  return NextResponse.json(report);
}
