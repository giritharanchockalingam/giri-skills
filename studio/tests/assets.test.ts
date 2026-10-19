import { test } from "node:test";
import assert from "node:assert/strict";
import { discoverAssets } from "../lib/github/assets.ts";

test("assets: skills, MCP endpoint + SDK, client configs, agent frameworks and definitions, instructions — each with evidence", () => {
  const paths = ["skills/build/safe-fix/SKILL.md", "vendor/grill-me/SKILL.md", "node_modules/x/SKILL.md", "studio/app/api/mcp/[[...scope]]/route.ts",
    ".mcp.json", ".claude/agents/reviewer.md", "AGENTS.md", "CLAUDE.md", "src/index.ts"];
  const pkg = JSON.stringify({ dependencies: { "@modelcontextprotocol/sdk": "1", "@langchain/langgraph": "0.2", next: "15" } });
  const a = discoverAssets(paths, { packageJson: pkg, requirements: "crewai==0.80\nrequests" });
  const by = (k: string) => a.filter((x) => x.kind === k);
  assert.deepEqual(by("skill").map((x) => [x.name, x.detail]), [["safe-fix", "skill"], ["grill-me", "vendored skill"]], "node_modules ignored");
  assert.equal(by("mcp_server").length, 1);
  assert.equal(by("mcp_server")[0].name, "MCP endpoint /api/mcp");
  assert.equal(by("mcp_server")[0].path, "studio/app/api/mcp");
  assert.ok(by("mcp_server")[0].evidence.includes("package.json: @modelcontextprotocol/sdk"));
  assert.deepEqual(by("mcp_config").map((x) => x.path), [".mcp.json"]);
  assert.deepEqual(by("agent").map((x) => x.name), ["LangGraph", "CrewAI", "reviewer"]);
  assert.deepEqual(by("agent_instructions").map((x) => x.name), ["AGENTS.md", "CLAUDE.md"]);
  for (const x of a) assert.ok(x.evidence.length > 0, `${x.kind} ${x.name} has evidence`);
});

test("assets: nothing from names alone — no deps, no files, no assets; AI SDK alone is not an agent", () => {
  assert.deepEqual(discoverAssets(["src/agent-utils.md", "README.md"]), []);
  assert.deepEqual(discoverAssets(["src/index.ts"], { packageJson: JSON.stringify({ dependencies: { ai: "4" } }) }), []);
});

test("assets: fixtures, templates and skill metadata are not live assets (found on the real giri-skills repo)", () => {
  const paths = [
    "skills/build/project-bootstrap/assets/CLAUDE.md", "skills/build/project-bootstrap/evals/fixtures/repo-existing/CLAUDE.md",
    "skills/ai-platform/mcp-server-builder/evals/fixtures/existing-server/server.py", "skills/x/evals/fixtures/s/SKILL.md",
    "vendor/grill-me/SKILL.md", "vendor/grill-me/agents/openai.yaml", "studio/app/api/mcp/[[...scope]]/route.ts", "studio/app/api/mcp/role/x.ts",
    "AGENTS.md", "src/crew/config/agents.yaml", ".claude/agents/reviewer.md"];
  const a = discoverAssets(paths);
  assert.deepEqual(a.map((x) => [x.kind, x.name]), [
    ["skill", "grill-me"],
    ["mcp_server", "MCP endpoint /api/mcp"],
    ["agent", "reviewer"], ["agent", "src/crew/config"],
    ["agent_instructions", "AGENTS.md"],
  ]);
  assert.equal(a.find((x) => x.kind === "mcp_server")!.evidence.length, 2, "one endpoint, both route files as evidence");
});
