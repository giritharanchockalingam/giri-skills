/* Port as an invisible catalog source, the pure part: Port blueprints + entities → Skills Factory catalog components
 * and relations. A Port entity that is the same thing as one Skills Factory already holds (a GitHub repository it
 * scanned) is not duplicated: it becomes an alias, so Port's relations attach to the existing entry. No I/O. */

import { isLocalArtifact } from "../../github/detect.ts";

export interface PortBlueprint { identifier: string; title?: string; schema?: { properties?: Record<string, { title?: string; type?: string; format?: string }> }; relations?: Record<string, { target?: string; title?: string }> }
export interface PortEntity {
  identifier: string; title?: string | null; blueprint?: string; properties?: Record<string, unknown>;
  relations?: Record<string, string | string[] | null>; updatedAt?: string; createdAt?: string;
}
export interface ComponentRow {
  kind: "component"; source: "port"; key: string; external_id: string; title: string; url: string; owner: null; archived: false;
  last_activity_at: string | null; properties: Record<string, unknown>;
}
export interface Ref { kind: string; key: string }
export interface PortRelation { from: Ref; to: Ref; evidence: string }

/** Port's own system types and the skill types Skills Factory itself publishes are not catalog components. */
export const SKIP_BLUEPRINTS = new Set(["aiSkill", "skill"]);
export const skipBlueprint = (id: string) => id.startsWith("_") || SKIP_BLUEPRINTS.has(id);

const GH_REPO = /^https:\/\/github\.com\/([^/\s]+)\/([^/\s#?]+?)(?:\.git)?\/?$/i;
const LINK_PROPS = ["url", "link", "htmlUrl", "html_url", "web_url", "webUrl"];

/** The page a person would open for this entity (its own link), else the given fallback. */
export function linkOf(e: PortEntity, fallback: string): string {
  for (const k of LINK_PROPS) { const v = e.properties?.[k]; if (typeof v === "string" && /^https:\/\//.test(v)) return v.slice(0, 1000); }
  return fallback;
}

/** "org/repo" when the entity is a GitHub repository (its url is the repository root). */
export function repoKeyOf(e: PortEntity): string | null {
  const u = e.properties?.url ?? e.properties?.link;
  const m = typeof u === "string" ? GH_REPO.exec(u.trim()) : null;
  return m ? `${m[1]}/${m[2]}`.toLowerCase() : null;
}

/** A short, single-line value worth showing; file contents and long text (a .gitignore, a README) are not "details". */
const scalar = (v: unknown): string | null =>
  typeof v === "string" ? (!v.trim() || /\n/.test(v.trim()) || isLocalArtifact(v) ? null : v.length > 140 ? `${v.slice(0, 137)}…` : v) : typeof v === "number" || typeof v === "boolean" ? String(v) : null;

export function mapPortCatalog(input: { blueprints: PortBlueprint[]; entities: Map<string, PortEntity[]>; nativeRepoKeys: Set<string>; fallbackUrl: string; now?: number }):
  { components: ComponentRow[]; aliases: number; relations: PortRelation[] } {
  const bpTitle = new Map(input.blueprints.map((b) => [b.identifier, b.title || b.identifier]));
  const propTitle = (bp: string, p: string) => input.blueprints.find((b) => b.identifier === bp)?.schema?.properties?.[p]?.title || p;
  const refOf = new Map<string, Ref>();           // "bp:identifier" → where it lives in Skills Factory
  const components: ComponentRow[] = [];
  let aliases = 0;
  for (const [bp, list] of input.entities) {
    if (skipBlueprint(bp)) continue;
    for (const e of list) {
      if (!e?.identifier) continue;
      const repo = repoKeyOf(e);
      if (repo && input.nativeRepoKeys.has(repo)) { refOf.set(`${bp}:${e.identifier}`, { kind: "repository", key: repo }); aliases++; continue; }
      const key = `${bp}:${e.identifier}`.slice(0, 200);
      refOf.set(`${bp}:${e.identifier}`, { kind: "component", key });
      const facts = Object.entries(e.properties ?? {})
        .filter(([k]) => !LINK_PROPS.includes(k))
        .map(([k, v]) => ({ label: propTitle(bp, k), value: scalar(v) }))
        .filter((f): f is { label: string; value: string } => !!f.value)
        .slice(0, 12);
      components.push({
        kind: "component", source: "port", key, external_id: e.identifier.slice(0, 200), title: (e.title || e.identifier).slice(0, 300),
        url: linkOf(e, input.fallbackUrl), owner: null, archived: false, last_activity_at: e.updatedAt ?? e.createdAt ?? null,
        properties: { type: bpTitle.get(bp), type_id: bp, facts },
      });
    }
  }
  // relation targets: the blueprint says which type each relation points to; fall back to the identifier alone
  const byId = new Map<string, Ref>();
  for (const [k, r] of refOf) { const id = k.slice(k.indexOf(":") + 1); if (!byId.has(id)) byId.set(id, r); }
  const targetOf = (bp: string, rel: string) => input.blueprints.find((b) => b.identifier === bp)?.relations?.[rel]?.target;
  const relations: PortRelation[] = [];
  for (const [bp, list] of input.entities) {
    if (skipBlueprint(bp)) continue;
    for (const e of list) {
      const from = refOf.get(`${bp}:${e.identifier}`);
      if (!from) continue;
      for (const [name, targets] of Object.entries(e.relations ?? {})) {
        for (const t of (Array.isArray(targets) ? targets : targets ? [targets] : [])) {
          const tbp = targetOf(bp, name);
          const to = (tbp ? refOf.get(`${tbp}:${t}`) : undefined) ?? byId.get(t);
          if (to && !(to.kind === from.kind && to.key === from.key)) relations.push({ from, to, evidence: `${bpTitle.get(bp)} → ${name}` });
        }
      }
    }
  }
  return { components, aliases, relations };
}
