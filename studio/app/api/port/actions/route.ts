/* POST /api/port/actions — Port's "Run skill" self-service action calls this webhook.
 * 1. Verifies Port's signature (HMAC with PORT_CLIENT_SECRET) and rejects stale or unsigned requests.
 * 2. Acknowledges at once (202), then runs the PUBLISHED skill exactly as /api/v1 does, under PORT_SF_API_KEY: same
 *    input validation, policy limits, pinning and audit. The Port run id is the idempotency key, so a retried webhook
 *    never runs a skill twice.
 * 3. Reports back to Port: progress logs, a link to the run in Skills Factory, and SUCCESS / FAILURE. */
import { after } from "next/server";
import { NextResponse } from "next/server";
import { verifyPortSignature } from "@/lib/integrations/port/signature";
import { parsePortRun } from "@/lib/integrations/port/map";
import { PortClient, portConfig } from "@/lib/integrations/port/client";
import { callerFromKey } from "@/lib/factory/apikey";
import { runPublishedSkill } from "@/lib/factory/apiRun";
import { log } from "@/lib/logger";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

const reply = (status: number, body: Record<string, unknown>) => NextResponse.json(body, { status });

export async function POST(req: Request) {
  const cfg = portConfig(process.env);
  const key = process.env.PORT_SF_API_KEY?.trim();
  if (!cfg.ok || !key) return reply(503, { error: "Port integration is not configured on this server", missing: [...(cfg.ok ? [] : cfg.missing), ...(key ? [] : ["PORT_SF_API_KEY"])] });

  const raw = (await req.text()).slice(0, 1_000_000);
  const bad = verifyPortSignature({ secret: cfg.clientSecret, timestamp: req.headers.get("x-port-timestamp"), signature: req.headers.get("x-port-signature"), rawBody: raw, nowSec: Math.floor(Date.now() / 1000) });
  if (bad) { log.warn({ action: "port.webhook.rejected", reason: bad }, "port webhook rejected"); return reply(401, { error: `signature check failed: ${bad}` }); }

  let parsed: ReturnType<typeof parsePortRun>;
  try { parsed = parsePortRun(JSON.parse(raw)); } catch { parsed = "body is not JSON"; }
  if (typeof parsed === "string") return reply(400, { error: parsed });
  const run = parsed;
  const base = new URL(req.url).origin;

  after(async () => {
    const port = new PortClient(cfg);
    const end = async (status: "SUCCESS" | "FAILURE", message: string, label: string) => {
      try { await port.runLog(run.portRunId, message, { status, label }); } catch (e) { log.error({ action: "port.run.report_failed", run: run.portRunId, err: e }, "could not report to Port"); }
    };
    try {
      await port.runLog(run.portRunId, `Skills Factory: running the published version of “${run.skill}”${run.requestedBy ? ` for ${run.requestedBy}` : ""}.`);
      const caller = await callerFromKey(key);
      if (caller instanceof Response) return end("FAILURE", "PORT_SF_API_KEY is not a valid workspace key (revoked?).", "Not authorised");
      const out = await runPublishedSkill(caller, run.skill, { inputs: run.inputs }, `port:${run.portRunId}`, `${base}/api/v1/skills/${run.skill}/run`);
      const b = out.body as { run_id?: string; status?: string; checks?: { pass?: boolean }[]; error?: { code?: string; message?: string } };
      if (out.http >= 400 || !b.run_id) return end("FAILURE", `Rejected: ${b.error?.message ?? `HTTP ${out.http}`}`, b.error?.code ?? "Rejected");
      const link = `${base}/runs/${b.run_id}`;
      try { await port.runUpdate(run.portRunId, { link: [link] }); } catch (e) { log.warn({ action: "port.run.link_failed", err: e }, "could not attach link"); }
      const checks = b.checks ?? [];
      const passed = checks.filter((c) => c.pass).length;
      const summary = `Run ${b.run_id}: ${b.status} · ${passed}/${checks.length} output checks passed. Full result: ${link}`;
      await end(b.status === "succeeded" ? "SUCCESS" : "FAILURE", summary, b.status === "succeeded" ? `${passed}/${checks.length} checks passed` : String(b.status));
      log.info({ action: "port.run.done", port_run: run.portRunId, run: b.run_id, status: b.status }, "port run finished");
    } catch (e) {
      log.error({ action: "port.run.error", port_run: run.portRunId, err: e }, "port run failed");
      await end("FAILURE", `Skills Factory error: ${(e as Error).message}`, "Error");
    }
  });
  return reply(202, { accepted: true, port_run_id: run.portRunId });
}
