/* Data access for self-service actions and the Inbox (everything waiting on a person). Queries run as the signed-in
 * user (RLS); emails come from the workspace member directory, never from auth tables directly. */
import type { SupabaseClient } from "@supabase/supabase-js";

export interface ActionRow { id: string; entity_id: string | null; repo: string; skill: string; inputs: Record<string, unknown>; uses_model: boolean; reason: string;
  status: string; requested_by: string; decided_by: string | null; decided_at: string | null; decision_note: string | null; run_id: string | null; commit_sha: string | null; error: string | null; created_at: string;
  requested_by_email?: string | null; decided_by_email?: string | null }

async function emails(sb: SupabaseClient, ws: string): Promise<Map<string, string>> {
  const { data } = await sb.rpc("sf_member_directory", { p_workspace: ws });
  return new Map(((data ?? []) as { user_id: string; email: string }[]).map((m) => [m.user_id, m.email]));
}

export async function listActions(sb: SupabaseClient, ws: string, o: { entityId?: string; status?: string; limit?: number } = {}): Promise<ActionRow[]> {
  let q = sb.from("sf_action_runs").select("id, entity_id, repo, skill, inputs, uses_model, reason, status, requested_by, decided_by, decided_at, decision_note, run_id, commit_sha, error, created_at")
    .eq("workspace_id", ws).order("created_at", { ascending: false }).limit(o.limit ?? 50);
  if (o.entityId) q = q.eq("entity_id", o.entityId);
  if (o.status) q = q.eq("status", o.status);
  const [{ data }, who] = await Promise.all([q, emails(sb, ws)]);
  return ((data ?? []) as ActionRow[]).map((a) => ({ ...a, requested_by_email: who.get(a.requested_by) ?? null, decided_by_email: a.decided_by ? who.get(a.decided_by) ?? null : null }));
}

export interface InboxData {
  actions: ActionRow[];
  agentRuns: { id: string; agent: string; started_at: string; invoked_by_email: string | null }[];
  reviews: { slug: string; name: string; version: number; created_at: string }[];
  overdue: { id: string; title: string; owner: string; due_on: string }[];
}

/** What is waiting on a person in this workspace: action approvals, playbook approval gates, skill versions in review,
 *  and initiatives past their deadline. */
export async function loadInbox(sb: SupabaseClient, ws: string): Promise<InboxData> {
  const today = new Date().toISOString().slice(0, 10);
  const [actions, runs, agents, versions, inis, who] = await Promise.all([
    listActions(sb, ws, { status: "pending_approval", limit: 100 }),
    sb.from("sf_agent_runs").select("id, agent_version_id, invoked_by, created_at").eq("workspace_id", ws).eq("status", "awaiting_approval").order("created_at", { ascending: false }).limit(50),
    sb.from("sf_agent_versions").select("id, sf_agents!inner(name, workspace_id)").eq("sf_agents.workspace_id", ws),
    sb.from("sf_skill_versions").select("version, created_at, sf_skills!sf_skill_versions_skill_id_fkey(slug, name, workspace_id)").eq("status", "in_review").eq("workspace_id", ws).limit(50),
    sb.from("sf_initiatives").select("id, title, owner, due_on").eq("workspace_id", ws).eq("status", "active").lt("due_on", today).order("due_on"),
    emails(sb, ws),
  ]);
  const agentName = new Map(((agents.data ?? []) as unknown as { id: string; sf_agents: { name: string } }[]).map((v) => [v.id, v.sf_agents.name]));
  type V = { version: number; created_at: string; sf_skills: { slug: string; name: string } | null };
  return {
    actions,
    agentRuns: ((runs.data ?? []) as { id: string; agent_version_id: string; invoked_by: string; created_at: string }[]).map((r) => ({ id: r.id, agent: agentName.get(r.agent_version_id) ?? "playbook", started_at: r.created_at, invoked_by_email: who.get(r.invoked_by) ?? null })),
    reviews: ((versions.data ?? []) as unknown as V[]).filter((v) => v.sf_skills).map((v) => ({ slug: v.sf_skills!.slug, name: v.sf_skills!.name, version: v.version, created_at: v.created_at })),
    overdue: (inis.data ?? []) as InboxData["overdue"],
  };
}

export async function inboxCount(sb: SupabaseClient, ws: string): Promise<number> {
  const d = await loadInbox(sb, ws);
  return d.actions.length + d.agentRuns.length + d.reviews.length + d.overdue.length;
}
