/* Drain the Port outbox in the background of a server action (publish, retire, push). Never throws into the caller:
 * a failure stays in the outbox with its error and is retried by the next kick or by POST /api/port/sync. */
import { headers } from "next/headers";
import { adminConfigured, createAdminSupabase } from "@/lib/supabase/server-admin";
import { drainPortOutbox } from "./outbox";
import { portalBase, registryRepo } from "./env";
import { portConfig } from "./client";
import { log } from "@/lib/logger";

const DRAIN_LIMIT = 50;           // drainPortOutbox's default batch
const KICK_BUDGET_MS = 40_000;    // stays inside the 60 s function limit with room for the reconcile that follows

export async function kickPortSync(): Promise<void> {
  if (!portConfig(process.env).ok || !adminConfigured()) return;    // not set up: rows wait in the outbox, shown on Integrations
  try {
    const h = await headers();
    const admin = createAdminSupabase();
    const opts = { portalBase: portalBase({ url: "https://x", headers: h }), registryRepo: registryRepo() };
    // drain in passes of 50 until the outbox is empty, a pass makes no progress, or the time budget is spent — a full
    // push of every skill must not leave rows waiting for the next event (live finding 2026-10-24: 32 left pending)
    const until = Date.now() + KICK_BUDGET_MS;
    let passes = 0, synced = 0, failed = 0;
    while (Date.now() < until && passes < 10) {
      const r = await drainPortOutbox(admin, opts);
      passes++; synced += r.synced; failed += r.failed;
      if (r.picked < DRAIN_LIMIT || r.synced === 0) break;
    }
    log.info({ action: "port.outbox.kick", passes, synced, failed }, "port outbox kicked");
  } catch (e) { log.error({ action: "port.outbox.kick_failed", err: e }, "port outbox kick failed"); }
}
