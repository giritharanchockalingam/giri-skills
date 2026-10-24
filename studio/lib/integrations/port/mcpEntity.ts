/* WP5 — the factory's MCP server as Port knows it (spec §5.4): one entity of Port's built-in `_mcp_server` blueprint
 * (never a second blueprint). Its `allowed_tools` are kept equal to the workspace's PUBLISHED skills plus the two
 * discovery helpers, so a retired skill leaves the list on the next sync. The entity itself is created by the Port
 * admin when the connector is added (it holds the auth header); the factory only maintains the tool list. */
import type { PortClient } from "./client";

export const MCP_BLUEPRINT_ID = "_mcp_server";
export const HELPER_TOOLS = ["find_skill", "get_run"] as const;

export interface McpEntitySync { status: "updated" | "current" | "not-registered"; identifier?: string; tools?: number; added?: string[]; removed?: string[] }

/** The tool list Port should allow: published skill slugs (sorted, deduplicated) + helpers. */
export const allowedTools = (publishedSlugs: string[]) => [...HELPER_TOOLS, ...[...new Set(publishedSlugs)].filter((s) => !(HELPER_TOOLS as readonly string[]).includes(s)).sort()];

/** Is this `_mcp_server` entity the factory's? (its URL is <portal>/api/mcp, optionally scoped) */
export const isFactoryServer = (url: unknown, portalBase: string) => typeof url === "string" && url.replace(/\/$/, "").startsWith(`${portalBase.replace(/\/$/, "")}/api/mcp`);

export async function syncMcpServerEntity(port: PortClient, portalBase: string, publishedSlugs: string[]): Promise<McpEntitySync> {
  const { entities } = await port.listEntities(MCP_BLUEPRINT_ID, 200);
  const mine = entities.find((e) => isFactoryServer((e.properties as Record<string, unknown> | undefined)?.url, portalBase) && !String((e.properties as Record<string, unknown>).url).replace(/\/$/, "").match(/\/api\/mcp\/.+/));
  if (!mine) return { status: "not-registered" };
  const want = allowedTools(publishedSlugs);
  const have = Array.isArray((mine.properties as Record<string, unknown>).allowed_tools) ? ((mine.properties as Record<string, unknown>).allowed_tools as string[]) : [];
  const added = want.filter((t) => !have.includes(t)), removed = have.filter((t) => !want.includes(t));
  const identifier = String(mine.identifier);
  if (!added.length && !removed.length) return { status: "current", identifier, tools: want.length };
  // merge-upsert touches only allowed_tools: URL, headers (the auth secret reference) and exposure stay as the admin set them
  await port.upsertEntity(MCP_BLUEPRINT_ID, { identifier, properties: { allowed_tools: want } } as { identifier: string });
  return { status: "updated", identifier, tools: want.length, added, removed };
}
