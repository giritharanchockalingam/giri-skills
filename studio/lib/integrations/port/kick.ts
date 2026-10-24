/* Drain the Port outbox in the background of a server action (publish, retire, push). Never throws into the caller:
 * a failure stays in the outbox with its error and is retried by the next kick or by POST /api/port/sync. */
import { headers } from "next/headers";
import { adminConfigured, createAdminSupabase } from "@/lib/supabase/server-admin";
import { drainPortOutbox } from "./outbox";
import { portalBase, registryRepo } from "./env";
import { portConfig } from "./client";
import { log } from "@/lib/logger";

export async function kickPortSync(): Promise<void> {
  if (!portConfig(process.env).ok || !adminConfigured()) return;    // not set up: rows wait in the outbox, shown on Integrations
  try {
    const h = await headers();
    const r = await drainPortOutbox(createAdminSupabase(), { portalBase: portalBase({ url: "https://x", headers: h }), registryRepo: registryRepo() });
    log.info({ action: "port.outbox.kick", picked: r.picked, synced: r.synced, failed: r.failed }, "port outbox kicked");
  } catch (e) { log.error({ action: "port.outbox.kick_failed", err: e }, "port outbox kick failed"); }
}
