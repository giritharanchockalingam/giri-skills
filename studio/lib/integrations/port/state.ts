/* Outbox / link counters for the Integrations page (members read their own workspace under RLS). */
import type { SupabaseClient } from "@supabase/supabase-js";
import { MAX_ATTEMPTS, type OutboxRow } from "./outbox";

export interface PortSyncState { linked: number; lastSyncedAt: string | null; pending: number; failing: number; deadLettered: number; deadLetters: OutboxRow[] }

export async function portSyncState(sb: SupabaseClient, workspaceId: string): Promise<PortSyncState> {
  const [{ data: links }, { data: open }] = await Promise.all([
    sb.from("sf_port_links").select("last_synced_at").eq("workspace_id", workspaceId),
    sb.from("sf_port_outbox").select("*").eq("workspace_id", workspaceId).is("processed_at", null).order("created_at", { ascending: false }).limit(500),
  ]);
  const rows = (open ?? []) as OutboxRow[];
  const synced = ((links ?? []) as { last_synced_at: string | null }[]).map((l) => l.last_synced_at).filter((x): x is string => !!x).sort();
  return {
    linked: (links ?? []).length, lastSyncedAt: synced.at(-1) ?? null,
    pending: rows.filter((r) => r.attempts === 0).length, failing: rows.filter((r) => r.attempts > 0 && r.attempts < MAX_ATTEMPTS).length,
    deadLettered: rows.filter((r) => r.attempts >= MAX_ATTEMPTS).length, deadLetters: rows.filter((r) => r.attempts >= MAX_ATTEMPTS).slice(0, 50),
  };
}
