/* Minimal Port REST client (docs.port.io): token, blueprint, entity upsert, action-run logs and status. fetch is injected
 * so it is unit-tested; every error says which call failed and Port's message. */
export interface PortConfig { apiUrl: string; clientId: string; clientSecret: string }

export function portConfig(env: Record<string, string | undefined>): ({ ok: true } & PortConfig) | { ok: false; missing: string[] } {
  const id = env.PORT_CLIENT_ID?.trim(), secret = env.PORT_CLIENT_SECRET?.trim();
  const missing = [!id && "PORT_CLIENT_ID", !secret && "PORT_CLIENT_SECRET"].filter(Boolean) as string[];
  if (missing.length) return { ok: false, missing };
  return { ok: true, apiUrl: (env.PORT_API_URL?.trim() || "https://api.port.io").replace(/\/$/, ""), clientId: id!, clientSecret: secret! };
}

export class PortClient {
  private token: { value: string; until: number } | null = null;
  private cfg: PortConfig;
  private f: typeof fetch;
  constructor(cfg: PortConfig, f: typeof fetch = fetch) { this.cfg = cfg; this.f = f; }

  private async call(method: string, path: string, body?: unknown, auth = true): Promise<{ status: number; json: Record<string, unknown> }> {
    const headers: Record<string, string> = { "content-type": "application/json" };
    if (auth) headers.authorization = `Bearer ${await this.accessToken()}`;
    const r = await this.f(`${this.cfg.apiUrl}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    let json: Record<string, unknown> = {};
    try { json = (await r.json()) as Record<string, unknown>; } catch { /* empty body */ }
    return { status: r.status, json };
  }
  private fail(what: string, r: { status: number; json: Record<string, unknown> }): never {
    const msg = (r.json.message ?? r.json.error ?? "") as string;
    throw new Error(`Port ${what} failed (${r.status})${msg ? `: ${msg}` : ""}`);
  }

  async accessToken(): Promise<string> {
    if (this.token && this.token.until > Date.now()) return this.token.value;
    const r = await this.call("POST", "/v1/auth/access_token", { clientId: this.cfg.clientId, clientSecret: this.cfg.clientSecret }, false);
    const t = r.json.accessToken;
    if (r.status >= 400 || typeof t !== "string") this.fail("authentication (check PORT_CLIENT_ID / PORT_CLIENT_SECRET and PORT_API_URL region)", r);
    const ttl = typeof r.json.expiresIn === "number" ? r.json.expiresIn * 1000 : 50 * 60_000;
    this.token = { value: t as string, until: Date.now() + ttl - 60_000 };
    return t as string;
  }

  /** Create the blueprint; an existing one is left as is (Port returns 409 for a duplicate identifier). */
  async ensureBlueprint(bp: { identifier: string }): Promise<"created" | "exists"> {
    const r = await this.call("POST", "/v1/blueprints", bp);
    if (r.status === 201 || r.status === 200) return "created";
    if (r.status === 409) return "exists";
    this.fail(`create blueprint ${bp.identifier}`, r);
  }

  async upsertEntity(blueprint: string, entity: { identifier: string }): Promise<void> {
    const r = await this.call("POST", `/v1/blueprints/${encodeURIComponent(blueprint)}/entities?upsert=true&merge=true`, entity);
    if (r.status >= 400) this.fail(`upsert ${blueprint}/${entity.identifier}`, r);
  }

  /** Read-only GET used by discovery (WP0 tenant inventory): returns the status and Port's JSON body unparsed, so a
   *  route this account's plan or region does not offer (403/404) is reported as such rather than thrown. */
  async read(path: string): Promise<{ status: number; json: Record<string, unknown> }> { return this.call("GET", path); }

  /** Every blueprint (Port: GET /v1/blueprints → { blueprints }). */
  async listBlueprints(): Promise<Record<string, unknown>[]> {
    const r = await this.call("GET", "/v1/blueprints");
    if (r.status >= 400) this.fail("list blueprints", r);
    return (Array.isArray(r.json.blueprints) ? r.json.blueprints : []) as Record<string, unknown>[];
  }

  /** A blueprint's entities, paged through Port's search route (limit/from); falls back to the plain list route. */
  async listEntities(blueprint: string, max = 2000): Promise<{ entities: Record<string, unknown>[]; truncated: boolean }> {
    const out: Record<string, unknown>[] = [];
    let from: string | null = null;
    for (let page = 0; page < 40 && out.length < max; page++) {
      const r = await this.call("POST", `/v1/blueprints/${encodeURIComponent(blueprint)}/entities/search`, { limit: 500, ...(from ? { from } : {}) });
      if (r.status === 404 || r.status === 405) break;                                           // older API: no search route
      if (r.status >= 400) this.fail(`read ${blueprint} entities`, r);
      out.push(...((Array.isArray(r.json.entities) ? r.json.entities : []) as Record<string, unknown>[]));
      from = typeof r.json.next === "string" && r.json.next ? r.json.next : null;
      if (!from) return { entities: out.slice(0, max), truncated: false };
    }
    if (!out.length) {
      const r = await this.call("GET", `/v1/blueprints/${encodeURIComponent(blueprint)}/entities`);
      if (r.status >= 400) this.fail(`read ${blueprint} entities`, r);
      const all = (Array.isArray(r.json.entities) ? r.json.entities : []) as Record<string, unknown>[];
      return { entities: all.slice(0, max), truncated: all.length > max };
    }
    return { entities: out.slice(0, max), truncated: out.length >= max };
  }

  async runLog(runId: string, message: string, end?: { status: "SUCCESS" | "FAILURE"; label?: string }): Promise<void> {
    const body: Record<string, unknown> = { message: message.slice(0, 4000) };
    if (end) { body.terminationStatus = end.status; if (end.label) body.statusLabel = end.label.slice(0, 200); }
    const r = await this.call("POST", `/v1/actions/runs/${encodeURIComponent(runId)}/logs`, body);
    if (r.status >= 400) this.fail(`log to run ${runId}`, r);
  }

  async runUpdate(runId: string, patch: { status?: "SUCCESS" | "FAILURE"; statusLabel?: string; link?: string[] }): Promise<void> {
    const r = await this.call("PATCH", `/v1/actions/runs/${encodeURIComponent(runId)}`, patch);
    if (r.status >= 400) this.fail(`update run ${runId}`, r);
  }
}
