/* MCP servers over Streamable HTTP (stateless, JSON responses). Auth: `Authorization: Bearer sf_live_…` (a workspace
 * API key — the same key, limits and audit trail as /api/v1). Scopes: /api/mcp, /api/mcp/role/<slug>,
 * /api/mcp/team/<slug>, /api/mcp/stage/<id>. Protocol logic lives in lib/factory/mcp.ts (unit-tested). */
import { NextResponse } from "next/server";
import { authenticateApiKey, type ApiCaller } from "@/lib/factory/apikey";
import { runPublishedSkill } from "@/lib/factory/apiRun";
import { stripRuntimePaths, publicContract } from "@/lib/factory/publicShape";
import { handle, SUPPORTED_PROTOCOL_VERSIONS, RPC, type CatalogSkill, type LibraryInfo, type McpBackend, type McpScope } from "@/lib/factory/mcp";
import { ROLE_TEMPLATES, POOL_TEMPLATES, getRouter } from "@/lib/factory/talentData";
import { skills as repoSkills, STAGES } from "@/lib/data";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

type Lib = { id: string; card?: string; stage?: string | string[] | null; agent?: { modes?: Partial<Record<"new" | "existing", { bring: string }>> } | null };
const LIB = new Map((repoSkills as unknown as Lib[]).map((s) => [s.id, s]));
const library = (id: string): LibraryInfo | null => {
  const s = LIB.get(id);
  if (!s) return null;
  const modes = Object.fromEntries(Object.entries(s.agent?.modes ?? {}).map(([k, v]) => [k, { bring: v!.bring }]));
  return { id, card: s.card ?? "", stage: Array.isArray(s.stage) ? s.stage[0] : s.stage ?? null, modes };
};

const rpcError = (status: number, code: number, message: string, headers: Record<string, string> = {}) =>
  NextResponse.json({ jsonrpc: "2.0", id: null, error: { code, message } }, { status, headers });

async function roleSkills(caller: ApiCaller, slug: string): Promise<{ title: string; skills: string[] } | null> {
  const { data } = await caller.supabase.rpc("sf_api_talent", { p_key_hash: caller.keyHash, p_kind: "role", p_slug: slug });
  const spec = (data as { name?: string; spec?: { title?: string; skills?: string[] } } | null)?.spec;
  if (spec?.skills) return { title: spec.title ?? slug, skills: spec.skills };          // the workspace's published, tailored role
  const t = ROLE_TEMPLATES.find((r) => r.name === slug);
  return t ? { title: t.title, skills: t.skills } : null;
}

async function resolveScope(caller: ApiCaller, parts: string[]): Promise<McpScope | null> {
  if (parts.length === 0) return { kind: "workspace", slug: null, title: "every published skill in this workspace", skills: null };
  const [kind, slug] = parts;
  if (parts.length !== 2 || !/^[a-z0-9][a-z0-9-]{0,78}$/.test(slug ?? "")) return null;
  if (kind === "role") {
    const r = await roleSkills(caller, slug);
    return r ? { kind, slug, title: `the ${r.title} role`, skills: new Set(r.skills) } : null;
  }
  if (kind === "team") {
    const { data } = await caller.supabase.rpc("sf_api_talent", { p_key_hash: caller.keyHash, p_kind: "pool", p_slug: slug });
    const spec = (data as { spec?: { title?: string; members?: { role: string }[] } } | null)?.spec ?? POOL_TEMPLATES.find((p) => p.name === slug) ?? null;
    if (!spec?.members) return null;
    const skills = new Set<string>();
    for (const m of spec.members) for (const s of (await roleSkills(caller, m.role))?.skills ?? []) skills.add(s);
    return { kind, slug, title: `the ${spec.title ?? slug} team`, skills };
  }
  if (kind === "stage") {
    const st = STAGES.find((s) => s.id === slug);
    if (!st) return null;
    const skills = new Set([...LIB.values()].filter((s) => (Array.isArray(s.stage) ? s.stage.includes(slug) : s.stage === slug)).map((s) => s.id));
    return { kind, slug, title: `the ${st.name} stage`, skills };
  }
  return null;
}

export async function POST(req: Request, { params }: { params: Promise<{ scope?: string[] }> }) {
  // DNS-rebinding guard (MCP transport spec): a browser Origin must be this site
  const origin = req.headers.get("origin");
  if (origin && new URL(origin).host !== new URL(req.url).host) return rpcError(403, RPC.INVALID_REQUEST, "origin not allowed");
  const pv = req.headers.get("mcp-protocol-version");
  if (pv && !(SUPPORTED_PROTOCOL_VERSIONS as readonly string[]).includes(pv)) return rpcError(400, RPC.INVALID_REQUEST, `unsupported MCP-Protocol-Version ${pv}`);

  const caller = await authenticateApiKey(req);
  if (caller instanceof Response) {
    const body = await caller.json().catch(() => ({}));
    return NextResponse.json(body, { status: caller.status, headers: { "WWW-Authenticate": 'Bearer realm="skills-factory", error="invalid_token"' } });
  }
  const scope = await resolveScope(caller, (await params).scope ?? []);
  if (!scope) return rpcError(404, RPC.INVALID_PARAMS, "no such MCP server: use /api/mcp, /api/mcp/role/<slug>, /api/mcp/team/<slug> or /api/mcp/stage/<id>");

  let catalog: Promise<CatalogSkill[]> | null = null;
  const be: McpBackend = {
    scope, library,
    catalog: () => (catalog ??= (async () => {
      const { data, error } = await caller.supabase.rpc("sf_api_catalog", { p_key_hash: caller.keyHash });
      if (error) throw new Error(error.message);
      return (data ?? []) as CatalogSkill[];
    })()),
    route: (task, k) => getRouter().route(task, undefined, k).map((h) => ({ skill: h.skill, score: h.score })),
    run: (slug, args, idem) => runPublishedSkill(caller, slug, args as Record<string, unknown>, idem, req.url),
    getRun: async (id) => {
      if (!/^[0-9a-f-]{36}$/.test(id)) return { http: 400, body: { error: { code: "bad_request", message: "run_id must be a UUID" } } };
      const { data, error } = await caller.supabase.rpc("sf_api_run_get", { p_key_hash: caller.keyHash, p_run: id });
      if (error) return { http: 500, body: { error: { code: "query_failed", message: error.message } } };
      if (!data) return { http: 404, body: { error: { code: "not_found", message: "No such run for this key's workspace." } } };
      return { http: 200, body: stripRuntimePaths(publicContract(data as Record<string, unknown>)) as Record<string, unknown> };
    },
  };

  let msg: unknown;
  try { msg = JSON.parse(await req.text()); } catch { return rpcError(400, RPC.PARSE, "body is not valid JSON"); }
  const batch = Array.isArray(msg);
  const replies = (await Promise.all((batch ? (msg as unknown[]) : [msg]).map((m) => handle(m, be)))).filter((r) => r !== null);
  if (!replies.length) return new NextResponse(null, { status: 202 });
  return NextResponse.json(batch ? replies : replies[0], { headers: { "Cache-Control": "no-store" } });
}

// No server-initiated stream and no sessions: GET (SSE) and DELETE are not offered (MCP transport spec allows 405).
const notAllowed = () => new NextResponse(null, { status: 405, headers: { Allow: "POST" } });
export const GET = notAllowed;
export const DELETE = notAllowed;
