/* POST /api/port/actions — Port calls this to run a governed skill.
 * Two Port models are supported:
 *  - Workflows (current): body.mode = "sync". Port waits up to 10 s, so the skill runs inline and the result is the
 *    HTTP response (Port shows it in the workflow run). Runs longer than ~8 s answer 202 with a link and finish here.
 *  - Classic self-service actions: answered 202 at once; progress, a link and SUCCESS / FAILURE are reported back to
 *    the action run through Port's API.
 * Authentication: a Port webhook signature (HMAC with PORT_CLIENT_SECRET) runs as PORT_SF_API_KEY; or
 * `Authorization: Bearer sf_live_…` (a workspace API key kept as a Port secret) runs as that key. Either way the run
 * goes through the same path as /api/v1: published version only, input validation, limits, pins, audit. The Port run
 * id is the idempotency key, so a retried call never runs a skill twice. */
import { after, NextResponse } from "next/server";
import { verifyPortSignature } from "@/lib/integrations/port/signature";
import { parsePortRun } from "@/lib/integrations/port/map";
import { PortClient, portConfig } from "@/lib/integrations/port/client";
import { callerFromKey, type ApiCaller } from "@/lib/factory/apikey";
import { runPublishedSkill, type ApiRunOutcome } from "@/lib/factory/apiRun";
import { log } from "@/lib/logger";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

const SYNC_BUDGET_MS = 8_000;
const reply = (status: number, body: Record<string, unknown>) => NextResponse.json(body, { status });

type RunBody = { run_id?: string; status?: string; checks?: { pass?: boolean; check?: string }[]; outputs?: unknown; error?: { code?: string; message?: string; details?: unknown } };
const summarize = (out: ApiRunOutcome, base: string) => {
  const b = out.body as RunBody;
  const checks = b.checks ?? [];
  const passed = checks.filter((c) => c.pass).length;
  return { b, passed, total: checks.length, link: b.run_id ? `${base}/runs/${b.run_id}` : null };
};

export async function POST(req: Request) {
  const raw = (await req.text()).slice(0, 1_000_000);
  const base = new URL(req.url).origin;
  const cfg = portConfig(process.env);

  // who is calling: a bearer workspace key, or Port's signature (then the server's own Port key)
  let caller: ApiCaller | Response;
  let signed = false;
  const bearer = req.headers.get("authorization")?.match(/^Bearer\s+(\S+)$/i)?.[1];
  if (bearer) caller = await callerFromKey(bearer);
  else {
    if (!cfg.ok) return reply(503, { error: "Port integration is not configured on this server", missing: cfg.missing });
    const bad = verifyPortSignature({ secret: cfg.clientSecret, timestamp: req.headers.get("x-port-timestamp"), signature: req.headers.get("x-port-signature"), rawBody: raw, nowSec: Math.floor(Date.now() / 1000) });
    if (bad) { log.warn({ action: "port.webhook.rejected", reason: bad }, "port webhook rejected"); return reply(401, { error: `not authenticated: ${bad}` }); }
    const key = process.env.PORT_SF_API_KEY?.trim();
    if (!key) return reply(503, { error: "PORT_SF_API_KEY is not set on this server" });
    caller = await callerFromKey(key);
    signed = true;
  }
  if (caller instanceof Response) return caller;

  let parsed: ReturnType<typeof parsePortRun>;
  try { parsed = parsePortRun(JSON.parse(raw)); } catch { parsed = "body is not JSON"; }
  if (typeof parsed === "string") return reply(400, { error: parsed });
  const run = parsed;
  const exec = () => runPublishedSkill(caller as ApiCaller, run.skill, { inputs: run.inputs }, `port:${run.portRunId}`, `${base}/api/v1/skills/${run.skill}/run`);

  // ── Port workflows: answer within Port's 10-second window ──
  if (run.sync) {
    const work = exec();
    const timer = new Promise<"slow">((r) => setTimeout(() => r("slow"), SYNC_BUDGET_MS));
    const first = await Promise.race([work, timer]);
    if (first === "slow") {
      after(async () => { try { await work; } catch (e) { log.error({ action: "port.run.error", port_run: run.portRunId, err: e }, "port run failed"); } });
      return reply(202, { accepted: true, message: "Still running in Skills Factory; the result will be on the Runs page.", runs: `${base}/runs` });
    }
    const s = summarize(first, base);
    log.info({ action: "port.run.done", port_run: run.portRunId, run: s.b.run_id, status: s.b.status ?? s.b.error?.code }, "port workflow run");
    if (first.http >= 400 || !s.b.run_id) return reply(first.http >= 400 ? first.http : 500, { ok: false, error: s.b.error?.message ?? "rejected", code: s.b.error?.code ?? null, details: s.b.error?.details ?? null });
    return reply(200, { ok: s.b.status === "succeeded", status: s.b.status, checks_passed: `${s.passed}/${s.total}`, run_id: s.b.run_id, link: s.link, outputs: s.b.outputs ?? null });
  }

  // ── Classic self-service actions: acknowledge, then report to the action run ──
  if (!signed || !cfg.ok) return reply(400, { error: "classic actions must be signed by Port; workflows send mode: \"sync\"" });
  after(async () => {
    const port = new PortClient(cfg);
    const end = async (status: "SUCCESS" | "FAILURE", message: string, label: string) => {
      try { await port.runLog(run.portRunId, message, { status, label }); } catch (e) { log.error({ action: "port.run.report_failed", run: run.portRunId, err: e }, "could not report to Port"); }
    };
    try {
      await port.runLog(run.portRunId, `Skills Factory: running the published version of “${run.skill}”${run.requestedBy ? ` for ${run.requestedBy}` : ""}.`);
      const out = await exec();
      const s = summarize(out, base);
      if (out.http >= 400 || !s.b.run_id) return end("FAILURE", `Rejected: ${s.b.error?.message ?? `HTTP ${out.http}`}`, s.b.error?.code ?? "Rejected");
      try { await port.runUpdate(run.portRunId, { link: [s.link!] }); } catch (e) { log.warn({ action: "port.run.link_failed", err: e }, "could not attach link"); }
      await end(s.b.status === "succeeded" ? "SUCCESS" : "FAILURE", `Run ${s.b.run_id}: ${s.b.status} · ${s.passed}/${s.total} output checks passed. Full result: ${s.link}`, s.b.status === "succeeded" ? `${s.passed}/${s.total} checks passed` : String(s.b.status));
    } catch (e) {
      log.error({ action: "port.run.error", port_run: run.portRunId, err: e }, "port run failed");
      await end("FAILURE", `Skills Factory error: ${(e as Error).message}`, "Error");
    }
  });
  return reply(202, { accepted: true, port_run_id: run.portRunId });
}
