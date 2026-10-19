/* Integrations, the pure part: provider API records → catalog entities (services, databases) and relations, each
 * relation with the evidence it was learned from. No I/O; the fetchers (vercel.ts, supabase.ts) feed this. */

export interface VercelProject {
  id: string; name: string; framework?: string | null; createdAt?: number; updatedAt?: number;
  link?: { type?: string; org?: string; repo?: string; productionBranch?: string } | null;
  targets?: { production?: { alias?: string[]; readyState?: string; createdAt?: number } | null } | null;
  latestDeployments?: { readyState?: string; target?: string | null; createdAt?: number; url?: string }[];
}
export interface VercelDeployment { uid: string; created: number; state?: string; readyState?: string; target?: string | null; meta?: { githubCommitSha?: string; githubCommitRef?: string } }
export interface VercelEnv { key: string; value?: string; type?: string; target?: string[] | string }
export interface SupabaseProject { id?: string; ref?: string; name: string; region?: string; status?: string; created_at?: string; organization_id?: string; database?: { version?: string; postgres_engine?: string } }

export interface EntityRow { kind: "service" | "database"; source: "vercel" | "supabase"; key: string; external_id: string; title: string; url: string; owner: null; archived: false; last_activity_at: string | null; properties: Record<string, unknown> }
export interface RelationSpec { from: { kind: "service"; key: string }; to: { kind: "repository" | "database"; key: string }; type: "built_from" | "uses_database"; evidence: string; source: "vercel" }

const REF = /^https:\/\/([a-z0-9]{20})\.supabase\.co\/?$/;
const iso = (ms?: number | null) => (ms ? new Date(ms).toISOString() : null);

/** The Supabase project a Vercel project's settings point at — from a plain (non-secret) *SUPABASE_URL variable only;
 *  the value itself is never stored, only the project ref it names. */
export function supabaseRefs(envs: VercelEnv[]): { ref: string; key: string }[] {
  const out = new Map<string, string>();
  for (const e of envs) {
    if (e.type !== "plain" || !/SUPABASE_URL$/.test(e.key) || typeof e.value !== "string") continue;
    const m = REF.exec(e.value.trim());
    if (m && !out.has(m[1])) out.set(m[1], e.key);
  }
  return [...out.entries()].map(([ref, key]) => ({ ref, key }));
}

export function mapVercel(team: { slug: string | null }, projects: VercelProject[], deploys: Map<string, VercelDeployment[]>, envs: Map<string, VercelEnv[]>, now = Date.now()):
  { entities: EntityRow[]; relations: RelationSpec[] } {
  const entities: EntityRow[] = [], relations: RelationSpec[] = [];
  for (const p of projects) {
    const prod = (deploys.get(p.id) ?? []).filter((d) => (d.target ?? "production") === "production");
    const ready = prod.filter((d) => (d.readyState ?? d.state) === "READY");
    const failed = prod.filter((d) => (d.readyState ?? d.state) === "ERROR");
    const last = [...prod].sort((a, b) => b.created - a.created)[0];
    const in30 = (d: VercelDeployment) => d.created >= now - 30 * 86_400_000;
    const alias = p.targets?.production?.alias?.find((a) => !a.includes("-git-")) ?? null;
    const repo = p.link?.type === "github" && p.link.org && p.link.repo ? `${p.link.org}/${p.link.repo}` : null;
    entities.push({
      kind: "service", source: "vercel", key: p.name, external_id: p.id, title: p.name, url: team.slug ? `https://vercel.com/${team.slug}/${p.name}` : "https://vercel.com/dashboard",
      owner: null, archived: false, last_activity_at: iso(last?.created ?? p.updatedAt),
      properties: {
        framework: p.framework ?? null, production_url: alias ? `https://${alias}` : null, repo, production_branch: p.link?.productionBranch ?? null,
        last_deploy: last ? { state: last.readyState ?? last.state ?? null, at: iso(last.created), sha: last.meta?.githubCommitSha ?? null } : null,
        // production deployment times (90 days, newest first) — the true deploy-frequency source for linked repositories
        prod_deploys: ready.map((d) => iso(d.created)).filter(Boolean).slice(0, 300),
        deploys_30d: ready.filter(in30).length, failed_30d: failed.filter(in30).length,
      },
    });
    if (repo) relations.push({ from: { kind: "service", key: p.name }, to: { kind: "repository", key: repo }, type: "built_from", evidence: `Vercel Git link ${repo}${p.link?.productionBranch ? ` (${p.link.productionBranch})` : ""}`, source: "vercel" });
    for (const r of supabaseRefs(envs.get(p.id) ?? []))
      relations.push({ from: { kind: "service", key: p.name }, to: { kind: "database", key: r.ref }, type: "uses_database", evidence: `Vercel env ${r.key} → project ${r.ref}`, source: "vercel" });
  }
  return { entities, relations };
}

export function mapSupabase(projects: SupabaseProject[]): EntityRow[] {
  return projects.filter((p) => p.ref ?? p.id).map((p) => {
    const ref = (p.ref ?? p.id)!;
    return {
      kind: "database", source: "supabase", key: ref, external_id: ref, title: p.name, url: `https://supabase.com/dashboard/project/${ref}`,
      owner: null, archived: false, last_activity_at: null,
      properties: { region: p.region ?? null, status: p.status ?? null, postgres: p.database?.version ?? p.database?.postgres_engine ?? null, organization_id: p.organization_id ?? null, created_at: p.created_at ?? null },
    };
  });
}
