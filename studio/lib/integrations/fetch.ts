/* Integrations, the I/O part: read Vercel (projects, production deployments, which Supabase project each points at) and
 * Supabase (projects) with server-held read tokens. Read-only; tokens never leave the server or reach the client. */
import type { VercelProject, VercelDeployment, VercelEnv, SupabaseProject } from "./map";

type Fetch = typeof fetch;
export class IntegrationError extends Error { status: number; constructor(status: number, message: string) { super(message); this.status = status; } }

export function vercelConfig(env: Record<string, string | undefined> = process.env) {
  const token = env.VERCEL_TOKEN?.trim(), teamId = env.VERCEL_TEAM_ID?.trim() || null;
  return token ? { ok: true as const, token, teamId } : { ok: false as const, missing: ["VERCEL_TOKEN"] };
}
export function supabaseConfig(env: Record<string, string | undefined> = process.env) {
  const token = env.SUPABASE_ACCESS_TOKEN?.trim();
  return token ? { ok: true as const, token } : { ok: false as const, missing: ["SUPABASE_ACCESS_TOKEN"] };
}

async function getJson<T>(url: string, token: string, f: Fetch): Promise<T> {
  const r = await f(url, { headers: { Authorization: `Bearer ${token}`, Accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(20_000) });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { const j = (await r.json()) as { error?: { message?: string }; message?: string }; msg = `${r.status} ${j.error?.message ?? j.message ?? ""}`.trim(); } catch { /* not json */ }
    throw new IntegrationError(r.status, `${new URL(url).host}${new URL(url).pathname}: ${msg}`);
  }
  return (await r.json()) as T;
}

async function pool<T, R>(items: T[], n: number, fn: (t: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length); let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => { while (i < items.length) { const k = i++; out[k] = await fn(items[k]); } }));
  return out;
}

const V = "https://api.vercel.com";
export async function readVercel(cfg: { token: string; teamId: string | null }, f: Fetch = fetch, now = Date.now()) {
  const q = (extra: Record<string, string>) => new URLSearchParams({ ...(cfg.teamId ? { teamId: cfg.teamId } : {}), ...extra }).toString();
  const team = cfg.teamId ? await getJson<{ slug: string }>(`${V}/v2/teams/${cfg.teamId}`, cfg.token, f) : await getJson<{ user: { username: string } }>(`${V}/v2/user`, cfg.token, f).then((u) => ({ slug: u.user.username }));
  const projects: VercelProject[] = [];
  let from: string | null = null, pages = 0;
  do {
    const r: { projects: VercelProject[]; pagination?: { next: number | null } } = await getJson(`${V}/v10/projects?${q({ limit: "100", ...(from ? { from } : {}) })}`, cfg.token, f);
    projects.push(...r.projects);
    from = r.pagination?.next ? String(r.pagination.next) : null;
  } while (from && ++pages < 10);
  const since = String(now - 90 * 86_400_000);
  const deploys = new Map<string, VercelDeployment[]>(), envs = new Map<string, VercelEnv[]>();
  const problems: string[] = [];
  await pool(projects, 8, async (p) => {
    try { deploys.set(p.id, (await getJson<{ deployments: VercelDeployment[] }>(`${V}/v6/deployments?${q({ projectId: p.id, target: "production", since, limit: "100" })}`, cfg.token, f)).deployments); }
    catch (e) { problems.push(`${p.name} deployments: ${(e as Error).message}`); }
    try { envs.set(p.id, (await getJson<{ envs: VercelEnv[] }>(`${V}/v10/projects/${p.id}/env?${q({})}`, cfg.token, f)).envs); }
    catch (e) { problems.push(`${p.name} settings: ${(e as Error).message}`); }
  });
  return { team, projects, deploys, envs, problems, truncated: !!from };
}

export async function readSupabase(cfg: { token: string }, f: Fetch = fetch): Promise<SupabaseProject[]> {
  return getJson<SupabaseProject[]>("https://api.supabase.com/v1/projects", cfg.token, f);
}
