/* AI assets in a repository — skills, MCP servers, MCP client configs, agents and agent instructions — found from file
 * paths and root manifests. Pure and deterministic; every asset carries the file(s) that prove it. Nothing is inferred
 * from a name alone: a framework counts only when its package is a dependency, a definition only when its file exists. */

export type AssetKind = "skill" | "mcp_server" | "mcp_config" | "agent" | "agent_instructions";
export interface AiAsset { kind: AssetKind; name: string; path: string; detail: string; evidence: string[] }

export const ASSET_LABEL: Record<AssetKind, string> = {
  skill: "Skill", mcp_server: "MCP server", mcp_config: "MCP client config", agent: "Agent", agent_instructions: "Agent instructions",
};
const MAX_PER_KIND = 200;
const IGNORE = /(^|\/)(node_modules|\.next|\.venv|__pycache__|site-packages)\//;   // not build/ or dist/: real source folders use those names

function deps(pkg: string | null): Record<string, string> {
  if (!pkg) return {};
  try { const j = JSON.parse(pkg) as { dependencies?: Record<string, string>; devDependencies?: Record<string, string> }; return { ...j.dependencies, ...j.devDependencies }; }
  catch { return {}; }
}
const dir = (p: string) => p.split("/").slice(0, -1).join("/");
const base = (p: string) => p.split("/").pop() ?? p;

const AGENT_FRAMEWORKS: { id: string; label: string; npm?: RegExp; py?: RegExp }[] = [
  { id: "langgraph", label: "LangGraph", npm: /^@langchain\/langgraph$/, py: /\blanggraph\b/ },
  { id: "crewai", label: "CrewAI", py: /\bcrewai\b/ },
  { id: "autogen", label: "AutoGen", py: /\b(autogen|pyautogen|autogen-agentchat)\b/ },
  { id: "openai-agents", label: "OpenAI Agents SDK", npm: /^@openai\/agents$/, py: /\bopenai-agents\b/ },
  { id: "claude-agent-sdk", label: "Claude Agent SDK", npm: /^@anthropic-ai\/claude-agent-sdk$/, py: /\bclaude-agent-sdk\b/ },
  { id: "google-adk", label: "Google ADK", py: /\bgoogle-adk\b/ },
  { id: "mastra", label: "Mastra", npm: /^@mastra\/core$/ },
  { id: "vercel-ai", label: "Vercel AI SDK (agents)", npm: /^ai$/ },
];

export function discoverAssets(paths: string[], manifests: { packageJson?: string | null; requirements?: string | null; pyproject?: string | null } = {}): AiAsset[] {
  const P = paths.filter((p) => !IGNORE.test(p));
  const d = deps(manifests.packageJson ?? null);
  const py = `${manifests.requirements ?? ""}\n${manifests.pyproject ?? ""}`.toLowerCase();
  const out: AiAsset[] = [];
  const push = (a: AiAsset) => { if (out.filter((x) => x.kind === a.kind).length < MAX_PER_KIND) out.push(a); };

  // skills: every SKILL.md (agentskills.io format) — the folder is the skill
  for (const p of P.filter((x) => base(x) === "SKILL.md").sort()) {
    const folder = dir(p);
    push({ kind: "skill", name: base(folder) || "(root)", path: folder || ".", detail: folder.startsWith("vendor/") ? "vendored skill" : "skill", evidence: [p] });
  }

  // MCP servers: the SDK as a dependency, and/or an MCP endpoint route in the code
  const routes = P.filter((p) => /(^|\/)(app|pages|src\/app)\/api\/mcp(\/|$)|(^|\/)mcp[-_]?server[^/]*\.(ts|js|py)$|(^|\/)server\.py$/.test(p) && /mcp/i.test(p));
  const sdk = [...(d["@modelcontextprotocol/sdk"] ? ["package.json: @modelcontextprotocol/sdk"] : []), ...(/\b(mcp|fastmcp)\b/.test(py) ? ["python deps: mcp / fastmcp"] : [])];
  if (sdk.length || routes.length) {
    const where = routes.length ? dir(routes[0]) : ".";
    push({ kind: "mcp_server", name: routes.length ? `MCP endpoint ${where.replace(/^(.*\/)?(src\/)?(app|pages)\/api\//, "/api/").replace(/\[\[?\.\.\.[^\]]+\]?\]/, "*")}` : "MCP server", path: where,
      detail: sdk.length ? "built on the MCP SDK" : "MCP endpoint route", evidence: [...sdk, ...routes.slice(0, 3)] });
  }

  // MCP client configs: the servers this repo's own agents/IDE connect to
  for (const p of P.filter((x) => /(^|\/)(\.?mcp\.json|\.cursor\/mcp\.json|\.vscode\/mcp\.json|claude_desktop_config\.json)$/.test(x)).sort())
    push({ kind: "mcp_config", name: base(p), path: p, detail: "MCP servers this repository's agents or IDE connect to", evidence: [p] });

  // agents: frameworks in use (dependency proof) and agent definition files
  for (const f of AGENT_FRAMEWORKS) {
    const ev = [...(f.npm ? Object.keys(d).filter((k) => f.npm!.test(k)).map((k) => `package.json: ${k}`) : []), ...(f.py && f.py.test(py) ? [`python deps: ${f.id}`] : [])];
    if (f.id === "vercel-ai" && !P.some((p) => /agent/i.test(p))) continue;   // the AI SDK alone is an LLM SDK, not an agent
    if (ev.length) push({ kind: "agent", name: f.label, path: ".", detail: "agent framework in use", evidence: ev });
  }
  for (const p of P.filter((x) => /(^|\/)\.claude\/agents\/[^/]+\.md$|(^|\/)agents\/[^/]+\.(agent\.)?(ya?ml|json)$|(^|\/)crew\.ya?ml$/.test(x)).sort())
    push({ kind: "agent", name: base(p).replace(/\.(agent\.)?(md|ya?ml|json)$/, ""), path: p, detail: p.includes(".claude/agents/") ? "Claude Code subagent" : "agent definition", evidence: [p] });

  // agent instructions: files coding agents read in this repository
  for (const p of P.filter((x) => /(^|\/)(AGENTS\.md|CLAUDE\.md|GEMINI\.md|\.cursorrules|\.github\/copilot-instructions\.md)$/.test(x)).sort())
    push({ kind: "agent_instructions", name: base(p), path: p, detail: "instructions coding agents follow here", evidence: [p] });
  return out;
}
