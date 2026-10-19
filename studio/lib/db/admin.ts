/* Data access for the Administration page. Queries run as the signed-in user (RLS applies); callers pass ctx.supabase. */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { ApiKeyRow, AuditRow, ConnectionRow, PolicyRow } from "@/lib/factory/db";

export interface MemberDirectoryRow { user_id: string; email: string; role: string; created_at: string }
export interface AdminData { members: MemberDirectoryRow[]; keys: ApiKeyRow[]; connections: ConnectionRow[]; policy: PolicyRow | null; audit: AuditRow[] }

/** Members, API keys (only when includeKeys: administrators), connections, policy and the latest 100 audit events. */
export async function loadAdminData(sb: SupabaseClient, workspaceId: string, includeKeys: boolean): Promise<AdminData> {
  const [members, keys, conns, policy, audit] = await Promise.all([
    sb.rpc("sf_member_directory", { p_workspace: workspaceId }),
    includeKeys ? sb.from("sf_api_keys").select("*").eq("workspace_id", workspaceId).order("created_at", { ascending: false }) : Promise.resolve({ data: [] }),
    sb.from("sf_connections").select("*").eq("workspace_id", workspaceId).order("name"),
    sb.from("sf_policies").select("*").eq("workspace_id", workspaceId).maybeSingle(),
    sb.from("sf_audit_events").select("*").eq("workspace_id", workspaceId).order("created_at", { ascending: false }).limit(100),
  ]);
  return {
    members: (members.data ?? []) as MemberDirectoryRow[],
    keys: (keys.data ?? []) as ApiKeyRow[],
    connections: (conns.data ?? []) as ConnectionRow[],
    policy: (policy.data ?? null) as PolicyRow | null,
    audit: (audit.data ?? []) as AuditRow[],
  };
}

/** What the page shows when the user has no workspace yet. */
export const EMPTY_ADMIN_DATA: AdminData = { members: [], keys: [], connections: [], policy: null, audit: [] };
