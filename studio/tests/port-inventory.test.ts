import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/* The WP0 inventory script runs against a local stand-in for api.port.io so the real script, real HTTP client and real
 * Markdown writer are exercised end to end. The stand-in only answers the routes the script reads; nothing is written. */
test("port inventory script: read-only tenant inventory with §4.0 checks, no secrets in output", async () => {
  const seen: string[] = [];
  const server = createServer((req, res) => {
    seen.push(`${req.method} ${req.url}`);
    const send = (status: number, body: unknown) => { res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };
    if (req.method === "POST" && req.url === "/v1/auth/access_token") return send(200, { accessToken: "tok-should-never-appear", expiresIn: 10800 });
    if (req.url === "/v1/organization") return send(200, { organization: { name: "acl-proof", identifier: "org_1" } });
    if (req.url === "/v1/blueprints") return send(200, { blueprints: [
      { identifier: "_mcp_server", title: "MCP Server", schema: { properties: { url: {} } }, relations: {} },
      { identifier: "aiSkill", title: "AI Skill", schema: { properties: { version: {}, approved: {} } }, relations: {} },
      { identifier: "repository", title: "Repository", schema: { properties: { url: {} } }, relations: { team: {} } },
    ] });
    if (req.method === "POST" && req.url?.endsWith("/entities/search")) return send(200, { entities: [{ identifier: "a" }, { identifier: "b" }] });
    if (req.url === "/v1/actions") return send(200, { actions: [{ identifier: "run_ai_skill", title: "Run skill", trigger: { type: "self-service", operation: "DAY-2", blueprintIdentifier: "aiSkill" }, invocationMethod: { type: "WEBHOOK" } }] });
    if (req.url === "/v1/scorecards") return send(403, { message: "forbidden on this plan" });
    return send(404, { message: "no such route" });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const port = (server.address() as { port: number }).port;
  const out = join(mkdtempSync(join(tmpdir(), "port-inv-")), "inventory.md");
  try {
    // async: the stub server lives in this process, so the script must run while the event loop stays free
    await promisify(execFile)(process.execPath, ["--experimental-strip-types", "scripts/port-inventory.mts", out], {
      cwd: join(import.meta.dirname, ".."), timeout: 60_000,
      env: { ...process.env, PORT_CLIENT_ID: "id-should-never-appear", PORT_CLIENT_SECRET: "secret-should-never-appear", PORT_API_URL: `http://127.0.0.1:${port}` },
    });
  } finally { server.close(); }
  const md = readFileSync(out, "utf8");
  assert.ok(seen.every((s) => s.startsWith("GET ") || s.startsWith("POST /v1/auth") || s.endsWith("/entities/search")), `read-only calls only: ${seen.join(", ")}`);
  assert.doesNotMatch(md, /should-never-appear/, "no credential or token leaks into the inventory");
  assert.match(md, /Built-in `_mcp_server` blueprint present: \*\*yes\*\*/);
  assert.match(md, /Native Port skill blueprint present: \*\*no/);
  assert.match(md, /Factory `aiSkill` blueprint present: \*\*yes\*\*/);
  assert.match(md, /`aiSkill`: 2 entities/);
  assert.match(md, /`run_ai_skill` \| Run skill \| self-service\/DAY-2 \| aiSkill \| WEBHOOK/);
  assert.match(md, /\/v1\/scorecards → HTTP 403: forbidden on this plan \(not available/);
  assert.match(md, /plan \/ limits: \*\*not exposed/);
});
