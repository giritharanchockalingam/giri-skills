/* Access requests for the Inbox: admins see every pending request; everyone sees their own recent ones (RLS). */
import type { SupabaseClient } from "@supabase/supabase-js";

export interface AccessRequestRow {
  id: string; talent_id: string; role_name: string; skill: string | null; note: string; status: "pending" | "approved" | "declined";
  requested_by: string; requested_by_email: string | null; decided_by_email: string | null; decision_note: string | null; created_at: string; decided_at: string | null;
}

export async function loadAccessRequests(sb: SupabaseClient, ws: string): Promise<AccessRequestRow[]> {
  const [{ data }, { data: dir }] = await Promise.all([
    sb.from("sf_access_requests").select("id, talent_id, skill, note, status, requested_by, decided_by, decision_note, created_at, decided_at, sf_talent(name)")
      .eq("workspace_id", ws).order("created_at", { ascending: false }).limit(50),
    sb.rpc("sf_member_directory", { p_workspace: ws }),
  ]);
  const email = new Map(((dir ?? []) as { user_id: string; email: string }[]).map((m) => [m.user_id, m.email]));
  type Raw = Omit<AccessRequestRow, "role_name" | "requested_by_email" | "decided_by_email"> & { decided_by: string | null; sf_talent: { name: string } | null };
  return ((data ?? []) as unknown as Raw[]).map((r) => ({
    id: r.id, talent_id: r.talent_id, role_name: r.sf_talent?.name ?? "a job role", skill: r.skill, note: r.note, status: r.status,
    requested_by: r.requested_by, requested_by_email: email.get(r.requested_by) ?? null, decided_by_email: r.decided_by ? email.get(r.decided_by) ?? null : null,
    decision_note: r.decision_note, created_at: r.created_at, decided_at: r.decided_at,
  }));
}

export async function pendingAccessCount(sb: SupabaseClient, ws: string): Promise<number> {
  const { count } = await sb.from("sf_access_requests").select("id", { count: "exact", head: true }).eq("workspace_id", ws).eq("status", "pending");
  return count ?? 0;
}
