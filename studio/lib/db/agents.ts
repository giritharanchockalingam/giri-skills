/* Data access for agents, their versions and runs. Queries run as the signed-in user (RLS applies). */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { AgentRow, AgentRunRow, AgentVersionRow } from "@/lib/factory/agentRun";

export type AgentVersionSummary = Pick<AgentVersionRow, "id" | "agent_id" | "version" | "status" | "spec">;
export type AgentRunSummary = Pick<AgentRunRow, "id" | "agent_version_id" | "status" | "created_at">;
export type AgentRunListItem = Pick<AgentRunRow, "id" | "status" | "created_at" | "agent_version_id" | "cost_usd">;
export type AgentVersionWithAgent = AgentVersionRow & { sf_agents: { slug: string; name: string } };
export type AgentLink = Pick<AgentRow, "slug" | "name" | "description">;

/** The Agents index: every agent of the workspace, all versions visible to the user, and the 200 most recent runs. */
export async function listAgentsOverview(sb: SupabaseClient, workspaceId: string): Promise<{ agents: AgentRow[]; versions: AgentVersionSummary[]; runs: AgentRunSummary[] }> {
  const [aq, vq, rq] = await Promise.all([
    sb.from("sf_agents").select("*").eq("workspace_id", workspaceId).order("updated_at", { ascending: false }),
    sb.from("sf_agent_versions").select("id, agent_id, version, status, spec"),
    sb.from("sf_agent_runs").select("id, agent_version_id, status, created_at").eq("workspace_id", workspaceId).order("created_at", { ascending: false }).limit(200),
  ]);
  return { agents: (aq.data ?? []) as AgentRow[], versions: (vq.data ?? []) as AgentVersionSummary[], runs: (rq.data ?? []) as AgentRunSummary[] };
}

/** The six most recently updated agents (front door). */
export async function listRecentAgents(sb: SupabaseClient, workspaceId: string): Promise<AgentLink[]> {
  const { data } = await sb.from("sf_agents").select("slug, name, description").eq("workspace_id", workspaceId).order("updated_at", { ascending: false }).limit(6);
  return (data ?? []) as AgentLink[];
}

export async function getAgentBySlug(sb: SupabaseClient, workspaceId: string, slug: string): Promise<AgentRow | null> {
  const { data } = await sb.from("sf_agents").select("*").eq("workspace_id", workspaceId).eq("slug", slug).maybeSingle();
  return (data ?? null) as AgentRow | null;
}

/** Every version of an agent, newest first. */
export async function listAgentVersions(sb: SupabaseClient, agentId: string): Promise<AgentVersionRow[]> {
  const { data } = await sb.from("sf_agent_versions").select("*").eq("agent_id", agentId).order("version", { ascending: false });
  return (data ?? []) as AgentVersionRow[];
}

/** The 8 most recent runs across the given versions. */
export async function listRecentRunsForVersions(sb: SupabaseClient, versionIds: string[]): Promise<AgentRunListItem[]> {
  const { data } = await sb.from("sf_agent_runs").select("id, status, created_at, agent_version_id, cost_usd").in("agent_version_id", versionIds).order("created_at", { ascending: false }).limit(8);
  return (data ?? []) as AgentRunListItem[];
}

export async function getAgentRun(sb: SupabaseClient, workspaceId: string, id: string): Promise<AgentRunRow | null> {
  const { data } = await sb.from("sf_agent_runs").select("*").eq("id", id).eq("workspace_id", workspaceId).maybeSingle();
  return (data ?? null) as AgentRunRow | null;
}

/** One agent version with its agent's slug and name. */
export async function getAgentVersionWithAgent(sb: SupabaseClient, versionId: string): Promise<AgentVersionWithAgent> {
  const { data } = await sb.from("sf_agent_versions").select("*, sf_agents!inner(slug, name)").eq("id", versionId).single();
  return data as AgentVersionWithAgent;
}
