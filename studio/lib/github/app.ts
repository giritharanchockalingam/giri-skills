/* GitHub App client for the Context Lake. Server only.
 *
 * Identity model
 *  - The App (env GITHUB_APP_*) reads repositories through short-lived installation tokens (1 h), never a PAT.
 *  - Linking an installation to a workspace requires PROOF: the installing user authorises the App (OAuth during
 *    install) and we check that installation is in GET /user/installations for that user's token. A guessed
 *    installation_id cannot be claimed. Each installation links to exactly one workspace (DB unique constraint).
 *  - `state` round-trips the workspace through GitHub, HMAC-signed and short-lived.
 * Secrets: read from the environment only; never stored in the database, never logged, never sent to the browser. */
import { createHmac, createSign, timingSafeEqual } from "node:crypto";

export const GITHUB_API = "https://api.github.com";
export const GITHUB_WEB = "https://github.com";

export interface GithubConfig { appId: string; slug: string; privateKey: string; clientId: string; clientSecret: string; webhookSecret: string | null }

/** The App's configuration, or the names of the missing variables (the setup page explains them). */
export function githubConfig(env: Record<string, string | undefined> = process.env): { ok: true; cfg: GithubConfig } | { ok: false; missing: string[] } {
  const need = ["GITHUB_APP_ID", "GITHUB_APP_SLUG", "GITHUB_APP_PRIVATE_KEY", "GITHUB_APP_CLIENT_ID", "GITHUB_APP_CLIENT_SECRET"] as const;
  const missing = need.filter((k) => !env[k]?.trim());
  if (missing.length) return { ok: false, missing };
  return { ok: true, cfg: {
    appId: env.GITHUB_APP_ID!.trim(), slug: env.GITHUB_APP_SLUG!.trim(),
    privateKey: env.GITHUB_APP_PRIVATE_KEY!.replace(/\\n/g, "\n").trim(),          // Vercel UI keeps real newlines; .env files often escape them
    clientId: env.GITHUB_APP_CLIENT_ID!.trim(), clientSecret: env.GITHUB_APP_CLIENT_SECRET!.trim(),
    webhookSecret: env.GITHUB_WEBHOOK_SECRET?.trim() || null,
  } };
}

const b64url = (b: Buffer | string) => Buffer.from(b).toString("base64").replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");

/** App JWT (RS256), valid 9 minutes, backdated 60 s for clock skew — per GitHub's docs. */
export function appJwt(appId: string, privateKeyPem: string, nowS = Math.floor(Date.now() / 1000)): string {
  const head = b64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const body = b64url(JSON.stringify({ iat: nowS - 60, exp: nowS + 540, iss: appId }));
  const sig = createSign("RSA-SHA256").update(`${head}.${body}`).sign(privateKeyPem);
  return `${head}.${body}.${b64url(sig)}`;
}

// ───────────── signed state (workspace + user through the GitHub round trip) ─────────────
const stateKey = (clientSecret: string) => createHmac("sha256", "sf-github-state").update(clientSecret).digest();
export function signState(payload: { w: string; u: string }, clientSecret: string, nowMs = Date.now()): string {
  const body = b64url(JSON.stringify({ ...payload, t: nowMs }));
  return `${body}.${b64url(createHmac("sha256", stateKey(clientSecret)).update(body).digest())}`;
}
export function verifyState(state: string, clientSecret: string, nowMs = Date.now(), maxAgeMs = 15 * 60_000): { w: string; u: string } | null {
  const [body, mac] = state.split(".");
  if (!body || !mac) return null;
  const want = b64url(createHmac("sha256", stateKey(clientSecret)).update(body).digest());
  const a = Buffer.from(mac), b = Buffer.from(want);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  try {
    const p = JSON.parse(Buffer.from(body.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8")) as { w?: string; u?: string; t?: number };
    if (typeof p.w !== "string" || typeof p.u !== "string" || typeof p.t !== "number" || nowMs - p.t > maxAgeMs || p.t > nowMs + 60_000) return null;
    return { w: p.w, u: p.u };
  } catch { return null; }
}

// ───────────── HTTP ─────────────
export class GithubError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}
type Fetch = typeof fetch;

export async function gh<T>(path: string, auth: string, init: { method?: string; body?: unknown; fetchImpl?: Fetch; accept?: string } = {}): Promise<{ data: T; next: string | null }> {
  const res = await (init.fetchImpl ?? fetch)(path.startsWith("http") ? path : `${GITHUB_API}${path}`, {
    method: init.method ?? "GET",
    headers: { Accept: init.accept ?? "application/vnd.github+json", ...(auth ? { Authorization: auth } : {}), "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "skills-factory",
      ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = `${res.status}`;
    try { msg = `${res.status} ${((await res.json()) as { message?: string }).message ?? ""}`.trim(); } catch { /* not json */ }
    throw new GithubError(res.status, `GitHub ${init.method ?? "GET"} ${path.replace(GITHUB_API, "")}: ${msg}`);
  }
  const next = /<([^>]+)>;\s*rel="next"/.exec(res.headers.get("link") ?? "")?.[1] ?? null;
  const raw = /\.(raw|diff)\b/.test(init.accept ?? "");                       // raw file text or a unified diff
  return { data: (res.status === 204 ? null : raw ? await res.text() : await res.json()) as T, next };
}

/** Follow `Link: rel="next"` up to `maxPages`, collecting `pick(page)`. */
export async function paginate<P, T>(path: string, auth: string, pick: (page: P) => T[], maxPages = 10, fetchImpl?: Fetch): Promise<{ items: T[]; truncated: boolean }> {
  const items: T[] = [];
  let url: string | null = path, pages = 0;
  while (url && pages < maxPages) {
    const r: { data: P; next: string | null } = await gh<P>(url, auth, { fetchImpl });
    items.push(...pick(r.data));
    url = r.next; pages++;
  }
  return { items, truncated: !!url };
}

export async function installationToken(cfg: GithubConfig, installationId: number, fetchImpl?: Fetch): Promise<string> {
  const r = await gh<{ token: string }>(`/app/installations/${installationId}/access_tokens`, `Bearer ${appJwt(cfg.appId, cfg.privateKey)}`, { method: "POST", fetchImpl });
  return r.data.token;
}

export interface InstallationInfo { id: number; account: { login: string; type: string }; repository_selection: "all" | "selected"; suspended_at: string | null }
export const getInstallation = async (cfg: GithubConfig, id: number, fetchImpl?: Fetch) =>
  (await gh<InstallationInfo>(`/app/installations/${id}`, `Bearer ${appJwt(cfg.appId, cfg.privateKey)}`, { fetchImpl })).data;

/** OAuth code (from the install redirect) → user access token. */
export async function exchangeCode(cfg: GithubConfig, code: string, fetchImpl?: Fetch): Promise<string> {
  const res = await (fetchImpl ?? fetch)(`${GITHUB_WEB}/login/oauth/access_token`, {
    method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json", "User-Agent": "skills-factory" },
    body: JSON.stringify({ client_id: cfg.clientId, client_secret: cfg.clientSecret, code }), cache: "no-store",
  });
  const j = (await res.json().catch(() => ({}))) as { access_token?: string; error_description?: string; error?: string };
  if (!res.ok || !j.access_token) throw new GithubError(res.status, `GitHub sign-in failed: ${j.error_description ?? j.error ?? res.status}`);
  return j.access_token;
}

/** True when the signed-in GitHub user can access this installation (the ownership proof). */
export async function userCanAccessInstallation(userToken: string, installationId: number, fetchImpl?: Fetch): Promise<boolean> {
  const { items } = await paginate<{ installations: { id: number }[] }, { id: number }>("/user/installations?per_page=100", `Bearer ${userToken}`, (p) => p.installations, 5, fetchImpl);
  return items.some((i) => i.id === installationId);
}

export interface GhRepo {
  id: number; name: string; full_name: string; html_url: string; private: boolean; archived: boolean; fork: boolean;
  default_branch: string; language: string | null; topics?: string[]; description: string | null; pushed_at: string | null; owner: { login: string };
}
export const listInstallationRepos = (token: string, fetchImpl?: Fetch) =>
  paginate<{ repositories: GhRepo[] }, GhRepo>("/installation/repositories?per_page=100", `Bearer ${token}`, (p) => p.repositories, 10, fetchImpl);

export interface TreeFile { path: string; sha: string; size: number }

/** Every file in the default branch with its blob sha and size (GitHub caps very large trees: `truncated` says so). */
export async function repoTree(token: string, repo: GhRepo, fetchImpl?: Fetch): Promise<{ files: TreeFile[]; truncated: boolean }> {
  try {
    const r = await gh<{ tree: { path: string; type: string; sha: string; size?: number }[]; truncated: boolean }>(
      `/repos/${repo.full_name}/git/trees/${encodeURIComponent(repo.default_branch)}?recursive=1`, `Bearer ${token}`, { fetchImpl });
    return { files: r.data.tree.filter((t) => t.type === "blob").map((t) => ({ path: t.path, sha: t.sha, size: t.size ?? 0 })), truncated: r.data.truncated };
  } catch (e) {
    if (e instanceof GithubError && (e.status === 409 || e.status === 404)) return { files: [], truncated: false };   // empty repository
    throw e;
  }
}

/** Every path in the default branch. */
export async function repoPaths(token: string, repo: GhRepo, fetchImpl?: Fetch): Promise<{ paths: string[]; truncated: boolean }> {
  const t = await repoTree(token, repo, fetchImpl);
  return { paths: t.files.map((f) => f.path), truncated: t.truncated };
}

/** A blob's text (by sha, from the tree), or null for binary content. */
export async function blobText(token: string, fullName: string, sha: string, fetchImpl?: Fetch): Promise<string | null> {
  const r = await gh<string>(`/repos/${fullName}/git/blobs/${sha}`, `Bearer ${token}`, { fetchImpl, accept: "application/vnd.github.raw+json" });
  return r.data.includes("\u0000") ? null : r.data;
}

/** The commit the default branch points at (scorecards record what they scored). */
export async function headSha(token: string, repo: GhRepo, fetchImpl?: Fetch): Promise<string | null> {
  try { return (await gh<{ sha: string }>(`/repos/${repo.full_name}/commits/${encodeURIComponent(repo.default_branch)}`, `Bearer ${token}`, { fetchImpl })).data.sha; }
  catch (e) { if (e instanceof GithubError && (e.status === 409 || e.status === 404 || e.status === 422)) return null; throw e; }
}

/** Raw text of one file (≤ 1 MB), or null when absent. */
export async function fileText(token: string, fullName: string, path: string, fetchImpl?: Fetch): Promise<string | null> {
  try {
    const r = await gh<string>(`/repos/${fullName}/contents/${path.split("/").map(encodeURIComponent).join("/")}`, `Bearer ${token}`, { fetchImpl, accept: "application/vnd.github.raw+json" });
    return r.data;
  } catch (e) {
    if (e instanceof GithubError && e.status === 404) return null;
    throw e;
  }
}

// ───────────── Check Runs (automations report back on the commit / pull request) ─────────────
export async function createCheckRun(token: string, fullName: string, b: { name: string; head_sha: string; details_url?: string; external_id?: string }, fetchImpl?: Fetch): Promise<{ id: number; html_url: string }> {
  return (await gh<{ id: number; html_url: string }>(`/repos/${fullName}/check-runs`, `Bearer ${token}`, { method: "POST", body: { ...b, status: "in_progress", started_at: new Date().toISOString() }, fetchImpl })).data;
}
export async function completeCheckRun(token: string, fullName: string, id: number, b: { conclusion: "success" | "failure" | "neutral"; title: string; summary: string; details_url?: string }, fetchImpl?: Fetch): Promise<void> {
  await gh(`/repos/${fullName}/check-runs/${id}`, `Bearer ${token}`, { method: "PATCH", fetchImpl,
    body: { status: "completed", conclusion: b.conclusion, completed_at: new Date().toISOString(), details_url: b.details_url, output: { title: b.title, summary: b.summary } } });
}

/** What the App itself is allowed to do (for the setup panel): permissions, subscribed events, webhook active. */
export async function appInfo(cfg: GithubConfig, fetchImpl?: Fetch): Promise<{ permissions: Record<string, string>; events: string[] }> {
  const a = (await gh<{ permissions: Record<string, string>; events: string[] }>("/app", `Bearer ${appJwt(cfg.appId, cfg.privateKey)}`, { fetchImpl })).data;
  return { permissions: a.permissions ?? {}, events: a.events ?? [] };
}

export const getRepo = async (token: string, fullName: string, fetchImpl?: Fetch) =>
  (await gh<GhRepo>(`/repos/${fullName}`, `Bearer ${token}`, { fetchImpl })).data;
