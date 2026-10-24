// GET /api/port/scorecard?slugs=a,b — ensure the skill_quality scorecard exists (Bronze/Silver) and read back Port's
// computed level per skill. Operator token. This is the WP2 contract test: the levels come from Port, not from here.
import { NextResponse, type NextRequest } from "next/server";
import { operatorAuthorized } from "@/lib/integrations/port/serverAuth";
import { PortClient, portConfig } from "@/lib/integrations/port/client";
import { ensureSkillQualityScorecard, readbackLevels, SKILL_QUALITY_SCORECARD } from "@/lib/integrations/port/scorecard";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

export async function GET(req: NextRequest) {
  const auth = operatorAuthorized(req.headers.get("authorization"));
  if (!auth.ok) return NextResponse.json({ error: { code: "AUTH_REQUIRED", message: auth.message } }, { status: auth.status });
  const cfg = portConfig(process.env);
  if (!cfg.ok) return NextResponse.json({ error: { code: "NOT_CONFIGURED", message: `set ${cfg.missing.join(", ")}` } }, { status: 503 });
  const port = new PortClient(cfg);
  const slugs = (req.nextUrl.searchParams.get("slugs") ?? "").split(",").map((s) => s.trim()).filter((s) => /^[a-z0-9][a-z0-9-]{0,78}$/.test(s)).slice(0, 50);
  try {
    const scorecard = await ensureSkillQualityScorecard(port);
    const levels = await readbackLevels(port, slugs);
    return NextResponse.json({ scorecard, definition: { levels: SKILL_QUALITY_SCORECARD.levels.map((l) => l.title), rules: SKILL_QUALITY_SCORECARD.rules.map((r) => `${r.level}: ${r.identifier}`) }, gold: "not created — owner decision D3 pending", levels });
  } catch (e) { return NextResponse.json({ error: { code: "PORT", message: (e as Error).message } }, { status: 502 }); }
}
