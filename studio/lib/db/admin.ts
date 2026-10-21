/* Data access for the Administration page. Queries run as the signed-in user (RLS applies); callers pass ctx.supabase. */
import type { SupabaseClient } from "@supabase/supabase-js";
import { skillTitle } from "@/lib/names";
import type { ApiKeyRow, AuditRow, ConnectionRow, PolicyRow } from "@/lib/factory/db";

export interface MemberDirectoryRow { user_id: string; email: string; role: string; created_at: string }
export interface InvitationRow { id: string; email: string; role: string; created_at: string; expires_at: string }
export interface AdminData { members: MemberDirectoryRow[]; keys: ApiKeyRow[]; connections: ConnectionRow[]; policy: PolicyRow | null; audit: AuditRow[]; invites: InvitationRow[] }

/** Members, API keys (only when includeKeys: administrators), connections, policy and the latest 100 audit events. */
export async function loadAdminData(sb: SupabaseClient, workspaceId: string, includeKeys: boolean): Promise<AdminData> {
  const [members, keys, conns, policy, audit, invites] = await Promise.all([
    sb.rpc("sf_member_directory", { p_workspace: workspaceId }),
    includeKeys ? sb.from("sf_api_keys").select("*").eq("workspace_id", workspaceId).order("created_at", { ascending: false }) : Promise.resolve({ data: [] }),
    sb.from("sf_connections").select("*").eq("workspace_id", workspaceId).order("name"),
    sb.from("sf_policies").select("*").eq("workspace_id", workspaceId).maybeSingle(),
    sb.from("sf_audit_events").select("*").eq("workspace_id", workspaceId).order("created_at", { ascending: false }).limit(100),
    includeKeys ? sb.from("sf_invitations").select("id, email, role, created_at, expires_at").eq("workspace_id", workspaceId).is("accepted_at", null).is("revoked_at", null).gt("expires_at", new Date().toISOString()).order("created_at", { ascending: false }) : Promise.resolve({ data: [] }),
  ]);
  return {
    members: (members.data ?? []) as MemberDirectoryRow[],
    keys: (keys.data ?? []) as ApiKeyRow[],
    connections: (conns.data ?? []) as ConnectionRow[],
    policy: (policy.data ?? null) as PolicyRow | null,
    audit: (audit.data ?? []) as AuditRow[],
    invites: (invites.data ?? []) as InvitationRow[],
  };
}

/** What the page shows when the user has no workspace yet. */
export const EMPTY_ADMIN_DATA: AdminData = { members: [], keys: [], connections: [], policy: null, audit: [], invites: [] };

/** Skill titles and "Skill vN" labels for the audit log (ids people should not have to read). */
export async function auditNames(sb: SupabaseClient, workspaceId: string): Promise<{ skills: Map<string, string>; versions: Map<string, string> }> {
  const { data: sk } = await sb.from("sf_skills").select("id, name").eq("workspace_id", workspaceId);
  const skills = new Map(((sk ?? []) as { id: string; name: string }[]).map((s) => [s.id, skillTitle(s.name)]));
  const ids = [...skills.keys()];
  const { data: vs } = ids.length ? await sb.from("sf_skill_versions").select("id, skill_id, version").in("skill_id", ids) : { data: [] };
  const versions = new Map(((vs ?? []) as { id: string; skill_id: string; version: number }[]).map((v) => [v.id, `${skills.get(v.skill_id) ?? "skill"} v${v.version}`]));
  return { skills, versions };
}
